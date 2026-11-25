#include "custom_wake_word.h"
#include "audio_service.h"
#include "system_info.h"
#include "assets.h"
#include "settings.h"

#include <esp_log.h>
#include <esp_mn_iface.h>
#include <esp_mn_models.h>
#include <esp_mn_speech_commands.h>
#include <cJSON.h>
#include <algorithm>
#include <cmath>

#define TAG "CustomWakeWord"

namespace {
constexpr float kMinDetectionThreshold = 0.05f;
constexpr float kMaxDetectionThreshold = 0.50f;
// MultiNet clears its partial command state when this window expires.  The
// default asset value (3 seconds) makes a normal wake phrase unreliable when
// it happens to straddle a window boundary, so continuous wake-word detection
// uses a longer window and resets it explicitly at session boundaries.
constexpr int kContinuousWakeRecognitionWindowMs = 15000;
constexpr int kTimeoutOverlapMs = 2000;
}

CustomWakeWord::CustomWakeWord()
    : wake_word_opus_() {
}

CustomWakeWord::~CustomWakeWord() {
    if (multinet_model_data_ != nullptr && multinet_ != nullptr) {
        multinet_->destroy(multinet_model_data_);
        multinet_model_data_ = nullptr;
    }

    if (wake_word_encode_task_stack_ != nullptr) {
        heap_caps_free(wake_word_encode_task_stack_);
    }

    if (wake_word_encode_task_buffer_ != nullptr) {
        heap_caps_free(wake_word_encode_task_buffer_);
    }

    if (owns_models_ && models_ != nullptr) {
        esp_srmodel_deinit(models_);
    }
}

void CustomWakeWord::ParseWakenetModelConfig() {
    // Read index.json
    auto& assets = Assets::GetInstance();
    void* ptr = nullptr;
    size_t size = 0;
    if (!assets.GetAssetData("index.json", ptr, size)) {
        ESP_LOGE(TAG, "Failed to read index.json");
        return;
    }
    cJSON* root = cJSON_ParseWithLength(static_cast<char*>(ptr), size);
    if (root == nullptr) {
        ESP_LOGE(TAG, "Failed to parse index.json");
        return;
    }
    cJSON* multinet_model = cJSON_GetObjectItem(root, "multinet_model");
    if (cJSON_IsObject(multinet_model)) {
        cJSON* language = cJSON_GetObjectItem(multinet_model, "language");
        cJSON* duration = cJSON_GetObjectItem(multinet_model, "duration");
        cJSON* threshold = cJSON_GetObjectItem(multinet_model, "threshold");
        cJSON* commands = cJSON_GetObjectItem(multinet_model, "commands");
        if (cJSON_IsString(language)) {
            language_ = language->valuestring;
        }
        if (cJSON_IsNumber(duration)) {
            duration_ = duration->valueint;
        }
        if (cJSON_IsNumber(threshold)) {
            threshold_ = threshold->valuedouble;
        }
        if (cJSON_IsArray(commands)) {
            for (int i = 0; i < cJSON_GetArraySize(commands); i++) {
                cJSON* command = cJSON_GetArrayItem(commands, i);
                if (cJSON_IsObject(command)) {
                    cJSON* command_name = cJSON_GetObjectItem(command, "command");
                    cJSON* text = cJSON_GetObjectItem(command, "text");
                    cJSON* action = cJSON_GetObjectItem(command, "action");
                    if (cJSON_IsString(command_name) && cJSON_IsString(text) && cJSON_IsString(action)) {
                        commands_.push_back({command_name->valuestring, text->valuestring, action->valuestring});
                        ESP_LOGI(TAG, "Command: %s, Text: %s, Action: %s", command_name->valuestring, text->valuestring, action->valuestring);
                    }
                }
            }
        }
    }
    cJSON_Delete(root);
}


bool CustomWakeWord::Initialize(AudioCodec* codec, srmodel_list_t* models_list) {
    codec_ = codec;
    commands_.clear();

    if (models_list == nullptr) {
        language_ = "cn";
        models_ = esp_srmodel_init("model");
        owns_models_ = models_ != nullptr;
#ifdef CONFIG_CUSTOM_WAKE_WORD
        threshold_ = CONFIG_CUSTOM_WAKE_WORD_THRESHOLD / 100.0f;
        commands_.push_back({CONFIG_CUSTOM_WAKE_WORD, CONFIG_CUSTOM_WAKE_WORD_DISPLAY, "wake"});
#endif
    } else {
        models_ = models_list;
        ParseWakenetModelConfig();
    }

    Settings settings("wake_word", false);
    const int stored_threshold_percent = settings.GetInt("threshold_pct", -1);
    if (stored_threshold_percent >= static_cast<int>(kMinDetectionThreshold * 100) &&
        stored_threshold_percent <= static_cast<int>(kMaxDetectionThreshold * 100)) {
        threshold_ = stored_threshold_percent / 100.0f;
        ESP_LOGI(TAG, "Using persisted wake threshold %.3f", threshold_);
    }

    if (models_ == nullptr || models_->num == -1) {
        ESP_LOGE(TAG, "Failed to initialize wakenet model");
        return false;
    }

    // 初始化 multinet (命令词识别)
    mn_name_ = esp_srmodel_filter(models_, ESP_MN_PREFIX, language_.c_str());
    if (mn_name_ == nullptr) {
        ESP_LOGW(TAG, "Language '%s' multinet not found, falling back to any multinet model", language_.c_str());
        mn_name_ = esp_srmodel_filter(models_, ESP_MN_PREFIX, NULL);
    }
    if (mn_name_ == nullptr) {
        ESP_LOGE(TAG, "Failed to initialize multinet, mn_name is nullptr");
        ESP_LOGI(TAG, "Please refer to https://pcn7cs20v8cr.feishu.cn/wiki/CpQjwQsCJiQSWSkYEvrcxcbVnwh to add custom wake word");
        return false;
    }

    multinet_ = esp_mn_handle_from_name(mn_name_);
    duration_ = std::max(duration_, kContinuousWakeRecognitionWindowMs);
    multinet_model_data_ = multinet_->create(mn_name_, duration_);
    multinet_->set_det_threshold(multinet_model_data_, threshold_);
    const size_t chunksize = multinet_->get_samp_chunksize(multinet_model_data_);
    const size_t sample_rate = multinet_->get_samp_rate(multinet_model_data_);
    input_buffer_.reserve(chunksize);
    timeout_overlap_chunk_capacity_ = std::max<size_t>(
        1, (sample_rate * kTimeoutOverlapMs / 1000 + chunksize - 1) / chunksize);
    timeout_overlap_buffer_.resize(timeout_overlap_chunk_capacity_ * chunksize);
    ResetTimeoutOverlap();
    ESP_LOGI(TAG, "Continuous recognition window=%d ms overlap=%d ms (%zu chunks)",
             duration_, kTimeoutOverlapMs, timeout_overlap_chunk_capacity_);
    esp_mn_commands_clear();
    for (int i = 0; i < commands_.size(); i++) {
        esp_mn_commands_add(i + 1, commands_[i].command.c_str());
    }
    esp_mn_commands_update();
    
    multinet_->print_active_speech_commands(multinet_model_data_);
#if CONFIG_SEND_WAKE_WORD_DATA
    if (!wake_word_audio_cache_.Initialize(16000 * 2)) {
        ESP_LOGW(TAG, "Wake-word audio upload disabled: PSRAM cache allocation failed");
    }
#endif
    return true;
}

void CustomWakeWord::OnWakeWordDetected(std::function<void(const std::string& wake_word)> callback) {
    wake_word_detected_callback_ = callback;
}

bool CustomWakeWord::SetDetectionThreshold(float threshold) {
    if (!std::isfinite(threshold) || threshold < kMinDetectionThreshold ||
        threshold > kMaxDetectionThreshold || multinet_ == nullptr ||
        multinet_model_data_ == nullptr) {
        ESP_LOGW(TAG, "Rejected wake threshold %.3f", threshold);
        return false;
    }

    std::lock_guard<std::mutex> lock(input_buffer_mutex_);
    const float previous = threshold_;
    threshold_ = threshold;
    multinet_->set_det_threshold(multinet_model_data_, threshold_);
    Settings settings("wake_word", true);
    settings.SetInt("threshold_pct", static_cast<int>(std::lround(threshold_ * 100.0f)));
    ESP_LOGI(TAG, "Wake threshold changed: %.3f -> %.3f", previous, threshold_);
    return true;
}

std::vector<std::string> CustomWakeWord::GetWakeWords() const {
    std::vector<std::string> words;
    if (multinet_model_data_ == nullptr) {
        return words;
    }
    for (const auto& command : commands_) {
        if (command.action == "wake" && !command.text.empty()) {
            words.push_back(command.text);
        }
    }
    return words;
}

void CustomWakeWord::Start() {
    {
        std::lock_guard<std::mutex> lock(input_buffer_mutex_);
        input_buffer_.clear();
        ResetTimeoutOverlap();
        multinet_->clean(multinet_model_data_);
        running_ = true;
    }
    ESP_LOGI(TAG, "Wake-word detection started: model=%s language=%s threshold=%.3f commands=%zu",
             mn_name_ ? mn_name_ : "none", language_.c_str(), threshold_, commands_.size());
}

void CustomWakeWord::Stop() {
    running_ = false;
    {
        std::lock_guard<std::mutex> lock(input_buffer_mutex_);
        input_buffer_.clear();
        ResetTimeoutOverlap();
        multinet_->clean(multinet_model_data_);
    }
    ESP_LOGI(TAG, "Wake-word detection stopped");
}

void CustomWakeWord::Feed(const std::vector<int16_t>& data) {
    FeedSamples(data.data(), data.size(), false);
}

void CustomWakeWord::FeedMono(const int16_t* data, size_t samples) {
    FeedSamples(data, samples, true);
}

void CustomWakeWord::ResetTimeoutOverlap() {
    timeout_overlap_chunk_count_ = 0;
    timeout_overlap_next_chunk_ = 0;
}

void CustomWakeWord::RememberTimeoutOverlap(const int16_t* samples, size_t sample_count) {
    if (timeout_overlap_chunk_capacity_ == 0 || timeout_overlap_buffer_.empty() ||
        samples == nullptr || sample_count == 0) {
        return;
    }
    const size_t chunksize = multinet_->get_samp_chunksize(multinet_model_data_);
    if (sample_count != chunksize) {
        return;
    }
    std::copy_n(samples, chunksize,
                timeout_overlap_buffer_.begin() + timeout_overlap_next_chunk_ * chunksize);
    timeout_overlap_next_chunk_ =
        (timeout_overlap_next_chunk_ + 1) % timeout_overlap_chunk_capacity_;
    timeout_overlap_chunk_count_ =
        std::min(timeout_overlap_chunk_count_ + 1, timeout_overlap_chunk_capacity_);
}

bool CustomWakeWord::HandleDetectedCommand() {
    esp_mn_results_t* mn_result = multinet_->get_results(multinet_model_data_);
    for (int i = 0; i < mn_result->num && running_; i++) {
        const int command_index = mn_result->command_id[i] - 1;
        if (command_index < 0 || command_index >= static_cast<int>(commands_.size())) {
            ESP_LOGW(TAG, "Ignoring invalid command_id=%d", mn_result->command_id[i]);
            continue;
        }
        ESP_LOGI(TAG, "Custom wake word detected: command_id=%d, string=%s, prob=%f",
                 mn_result->command_id[i], mn_result->string, mn_result->prob[i]);
        auto& command = commands_[command_index];
        if (command.action == "wake") {
            last_detected_wake_word_ = command.text;
            running_ = false;
            input_buffer_.clear();
            ResetTimeoutOverlap();
            if (wake_word_detected_callback_) {
                wake_word_detected_callback_(last_detected_wake_word_);
            }
            return true;
        }
    }
    return false;
}

bool CustomWakeWord::ReplayTimeoutOverlap() {
    if (timeout_overlap_chunk_count_ == 0 || timeout_overlap_chunk_capacity_ == 0) {
        return false;
    }
    const size_t chunksize = multinet_->get_samp_chunksize(multinet_model_data_);
    const size_t oldest = timeout_overlap_chunk_count_ == timeout_overlap_chunk_capacity_
                              ? timeout_overlap_next_chunk_
                              : 0;
    for (size_t i = 0; i < timeout_overlap_chunk_count_ && running_; ++i) {
        const size_t chunk_index = (oldest + i) % timeout_overlap_chunk_capacity_;
        int16_t* chunk = timeout_overlap_buffer_.data() + chunk_index * chunksize;
        const esp_mn_state_t state = multinet_->detect(multinet_model_data_, chunk);
        if (state == ESP_MN_STATE_DETECTED) {
            const bool detected = HandleDetectedCommand();
            multinet_->clean(multinet_model_data_);
            return detected;
        }
        if (state == ESP_MN_STATE_TIMEOUT) {
            ESP_LOGW(TAG, "MultiNet timed out while replaying overlap audio");
            multinet_->clean(multinet_model_data_);
            return false;
        }
    }
    return false;
}

void CustomWakeWord::FeedSamples(const int16_t* data, size_t samples, bool mono) {
    if (multinet_model_data_ == nullptr || data == nullptr || samples == 0) {
        return;
    }

    std::lock_guard<std::mutex> lock(input_buffer_mutex_);
    // Check running state inside lock to avoid TOCTOU race with Stop()
    if (!running_) {
        return;
    }

    // If input channels is 2, we need to fetch the left channel data
    if (!mono && codec_->input_channels() > 1) {
        for (size_t i = 0; i < samples; i += codec_->input_channels()) {
            input_buffer_.push_back(data[i]);
        }
    } else {
        input_buffer_.insert(input_buffer_.end(), data, data + samples);
    }
    
    int chunksize = multinet_->get_samp_chunksize(multinet_model_data_);
    while (input_buffer_.size() >= chunksize) {
#if CONFIG_SEND_WAKE_WORD_DATA
        wake_word_audio_cache_.Store(input_buffer_.data(), chunksize);
#endif

        RememberTimeoutOverlap(input_buffer_.data(), chunksize);
        esp_mn_state_t mn_state = multinet_->detect(multinet_model_data_, input_buffer_.data());

        if (mn_state == ESP_MN_STATE_DETECTED) {
            HandleDetectedCommand();
            multinet_->clean(multinet_model_data_);
        } else if (mn_state == ESP_MN_STATE_TIMEOUT) {
            ESP_LOGD(TAG, "Command word detection timeout, replaying overlap");
            multinet_->clean(multinet_model_data_);
            ReplayTimeoutOverlap();
        }
        
        if (!running_) {
            break;
        }
        input_buffer_.erase(input_buffer_.begin(), input_buffer_.begin() + chunksize);
    }
}

size_t CustomWakeWord::GetFeedSize() {
    if (multinet_model_data_ == nullptr) {
        return 0;
    }
    return multinet_->get_samp_chunksize(multinet_model_data_);
}

void CustomWakeWord::EncodeWakeWordData() {
    const size_t stack_size = 4096 * 7;
    wake_word_opus_.clear();
    if (wake_word_encode_task_stack_ == nullptr) {
        wake_word_encode_task_stack_ = (StackType_t*)heap_caps_malloc(stack_size, MALLOC_CAP_SPIRAM);
        assert(wake_word_encode_task_stack_ != nullptr);
    }
    if (wake_word_encode_task_buffer_ == nullptr) {
        wake_word_encode_task_buffer_ = (StaticTask_t*)heap_caps_malloc(sizeof(StaticTask_t), MALLOC_CAP_INTERNAL);
        assert(wake_word_encode_task_buffer_ != nullptr);
    }

    wake_word_encode_task_ = xTaskCreateStatic([](void* arg) {
        auto this_ = (CustomWakeWord*)arg;
        {
            auto start_time = esp_timer_get_time();
            // Create encoder
            esp_opus_enc_config_t opus_enc_cfg = AS_OPUS_ENC_CONFIG();
            void* encoder_handle = nullptr;
            auto ret = esp_opus_enc_open(&opus_enc_cfg, sizeof(esp_opus_enc_config_t), &encoder_handle);
            if (encoder_handle == nullptr) {
                ESP_LOGE(TAG, "Failed to create audio encoder, error code: %d", ret);
                this_->wake_word_audio_cache_.Clear();
                std::lock_guard<std::mutex> lock(this_->wake_word_mutex_);
                this_->wake_word_opus_.push_back(std::vector<uint8_t>());
                this_->wake_word_cv_.notify_all();
                vTaskDelete(nullptr);
                return;
            }
            // Get frame size
            int frame_size = 0;
            int outbuf_size = 0;
            esp_opus_enc_get_frame_size(encoder_handle, &frame_size, &outbuf_size);
            frame_size = frame_size / sizeof(int16_t);
            // Encode all PCM data
            int packets = 0;
            std::vector<int16_t> in_buffer(frame_size);
            esp_audio_enc_in_frame_t in = {};
            esp_audio_enc_out_frame_t out = {};
            const size_t cached_samples = this_->wake_word_audio_cache_.Size();
            for (size_t offset = 0;
                 offset + static_cast<size_t>(frame_size) <= cached_samples;
                 offset += frame_size) {
                if (this_->wake_word_audio_cache_.Read(
                        offset, in_buffer.data(), frame_size) != static_cast<size_t>(frame_size)) {
                    break;
                }
                std::vector<uint8_t> opus_buf(outbuf_size);
                in.buffer = reinterpret_cast<uint8_t*>(in_buffer.data());
                in.len = frame_size * sizeof(int16_t);
                out.buffer = opus_buf.data();
                out.len = outbuf_size;
                out.encoded_bytes = 0;
                ret = esp_opus_enc_process(encoder_handle, &in, &out);
                if (ret == ESP_AUDIO_ERR_OK) {
                    std::lock_guard<std::mutex> lock(this_->wake_word_mutex_);
                    this_->wake_word_opus_.emplace_back(opus_buf.data(), opus_buf.data() + out.encoded_bytes);
                    this_->wake_word_cv_.notify_all();
                    packets++;
                } else {
                    ESP_LOGE(TAG, "Failed to encode audio, error code: %d", ret);
                }
            }
            this_->wake_word_audio_cache_.Clear();
            // Close encoder
            esp_opus_enc_close(encoder_handle);
            auto end_time = esp_timer_get_time();
            ESP_LOGI(TAG, "Encode wake word opus %d packets in %ld ms", packets, (long)((end_time - start_time) / 1000));

            std::lock_guard<std::mutex> lock(this_->wake_word_mutex_);
            this_->wake_word_opus_.push_back(std::vector<uint8_t>());
            this_->wake_word_cv_.notify_all();
        }
        vTaskDelete(NULL);
    }, "encode_wake_word", stack_size, this, 2, wake_word_encode_task_stack_, wake_word_encode_task_buffer_);
}

bool CustomWakeWord::GetWakeWordOpus(std::vector<uint8_t>& opus) {
    std::unique_lock<std::mutex> lock(wake_word_mutex_);
    wake_word_cv_.wait(lock, [this]() {
        return !wake_word_opus_.empty();
    });
    opus.swap(wake_word_opus_.front());
    wake_word_opus_.pop_front();
    return !opus.empty();
}
