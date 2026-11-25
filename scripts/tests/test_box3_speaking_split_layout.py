import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class Box3SpeakingSplitLayoutTest(unittest.TestCase):
    def test_box3_enables_speaking_split_layout(self):
        config = (ROOT / "main/boards/espressif/esp32-s3-box-3/config.json").read_text(
            encoding="utf-8"
        )
        self.assertIn("CONFIG_USE_SPEAKING_SPLIT_LAYOUT=y", config)
        defaults = (ROOT / "sdkconfig.oraki-box3.defaults").read_text(encoding="utf-8")
        self.assertIn("CONFIG_USE_SPEAKING_SPLIT_LAYOUT=y", defaults)

    def test_layout_is_always_split_and_uses_vertical_lyrics(self):
        display_header = (ROOT / "main/display/display.h").read_text(encoding="utf-8")
        lcd_header = (ROOT / "main/display/lcd_display.h").read_text(encoding="utf-8")
        lcd_source = (ROOT / "main/display/lcd_display.cc").read_text(encoding="utf-8")
        application_header = (ROOT / "main/application.h").read_text(encoding="utf-8")
        application = (ROOT / "main/application.cc").read_text(encoding="utf-8")
        cmake = (ROOT / "main/CMakeLists.txt").read_text(encoding="utf-8")

        self.assertIn("SetSpeakingLayout(bool speaking)", display_header)
        self.assertIn("SetSpeakingLayout(bool speaking) override", lcd_header)
        self.assertIn("LV_FLEX_FLOW_COLUMN", lcd_source)
        self.assertNotIn("speaking ? LV_FLEX_ALIGN_END : LV_FLEX_ALIGN_CENTER", lcd_source)
        self.assertIn("lv_obj_get_scroll_bottom(bottom_bar_)", lcd_source)
        self.assertIn("StartLyricScroll()", lcd_source)
        self.assertGreaterEqual(
            lcd_source.count(
                "lv_obj_set_style_text_align(chat_message_label_, LV_TEXT_ALIGN_CENTER, 0)"
            ),
            2,
        )
        self.assertIn("int LcdDisplay::GetSplitPanelLeft() const", lcd_source)
        self.assertIn("gif_controller_->width()", lcd_source)
        self.assertIn("kEmojiLeft + animation_width + kSplitPanelGap", lcd_source)
        self.assertNotIn("constexpr int kSplitPanelLeft = 112", lcd_source)
        self.assertIn("font_noto_sans_basic_16_4", lcd_source)
        self.assertIn(
            "elseif(CONFIG_BOARD_TYPE_ESP32_S3_BOX_3)\n"
            "    set(BOARD_DIR \"espressif/esp32-s3-box-3\")\n"
            "    set(BUILTIN_TEXT_FONT font_noto_sans_basic_16_4)",
            cmake,
        )
        self.assertIn("split_text_font_", lcd_header)
        self.assertIn("bool AddTextGlyphs", lcd_header)
        self.assertIn("split_text_font_.fallback", lcd_source)
        self.assertIn("bubble_tail_ = lv_obj_create(screen)", lcd_source)
        self.assertIn("lv_obj_set_style_transform_rotation(bubble_tail_, 450, 0)", lcd_source)
        self.assertIn(
            "lv_obj_align_to(bubble_tail_, emoji_box_, LV_ALIGN_OUT_RIGHT_MID",
            lcd_source,
        )
        self.assertIn("void LcdDisplay::UpdateSplitPanelSize()", lcd_source)
        self.assertIn("lv_obj_set_size(bottom_bar_, panel_width, panel_height)", lcd_source)
        self.assertIn("lv_obj_set_width(chat_message_label_, LV_SIZE_CONTENT)", lcd_source)
        self.assertNotIn(
            "lv_obj_set_size(bottom_bar_, width_ - kSplitPanelLeft, height_ - 52)",
            lcd_source,
        )
        self.assertIn(
            "lv_obj_set_style_text_align(chat_message_label_, LV_TEXT_ALIGN_LEFT, 0)",
            lcd_source,
        )
        self.assertIn("lv_obj_scroll_to_y", lcd_source)
        self.assertIn("LV_DIR_VER", lcd_source)
        self.assertIn("lv_obj_align(emoji_box_, LV_ALIGN_LEFT_MID, 8, 8)", lcd_source)
        self.assertIn('lv_label_set_text(brand_label_, "ORAKI")', lcd_source)
        self.assertIn("brand_label_ = lv_label_create(status_bar_)", lcd_source)
        self.assertIn("lv_obj_align(brand_label_, LV_ALIGN_CENTER, 0, 0)", lcd_source)
        self.assertIn("lv_obj_align(status_label_, LV_ALIGN_RIGHT_MID", lcd_source)
        self.assertNotIn("lv_obj_align_to(brand_label_, emoji_box_, LV_ALIGN_OUT_BOTTOM_MID", lcd_source)
        self.assertIn("lv_obj_set_style_text_color(brand_label_", lcd_source)
        self.assertIn('ResetSplitPanel("Say \\"Hi Oraki\\" to wake me")', lcd_source)
        self.assertIn("void LcdDisplay::SetStatus(const char* status)", lcd_source)
        self.assertIn("IsClockText(status)", lcd_source)
        self.assertIn("speaking_text_received_", application_header)
        self.assertIn("if (!speaking_text_received_)", application)
        self.assertIn("speaking_text_received_ = true", application)

    def test_every_state_has_english_right_panel_copy(self):
        application = (ROOT / "main/application.cc").read_text(encoding="utf-8")

        for copy in (
            'Say \\"Hi Oraki\\" to wake me',
            'Listening...',
            'Thinking...',
            'Executing...',
            'Preparing response...',
            'Speaking...',
            'Something went wrong',
        ):
            self.assertIn(copy, application)

        self.assertIn(
            'SetChatMessage("system", kIdleDisplayPrompt)', application
        )
        self.assertNotIn(
            'display->ShowNotification(message.c_str());\n        display->SetChatMessage("system", "");',
            application,
        )


if __name__ == "__main__":
    unittest.main()
