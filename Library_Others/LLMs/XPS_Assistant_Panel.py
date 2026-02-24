# XPS_Assistant_Panel.py - Simplified XPS AI Assistant
# Location: libraries/LLMs/XPS_Assistant_Panel.py
#
# This single file replaces:
#   - XPS_ChatGPT_Panel.py
#   - XPS_ChatGPT.py
#   - XPS_Assistant.py
#   - XPS_Knowledge.py (18MB database no longer generated)
#
# Usage in Widgets_Toolbars.py:
#   from libraries.LLMs.XPS_Assistant_Panel import open_xps_assistant
#
#   def on_open_chatgpt_assistant(window):
#       open_xps_assistant(None, window)

import wx
import wx.html
import wx.richtext
import threading
import sys
import os
import json
import re
import requests
import datetime
import numpy as np


class XPSAssistantFrame(wx.Frame):
    """Main frame for KherveAI Assistant with Mode menu"""

    def __init__(self, parent, window):
        super().__init__(parent, title="KherveAI: Your AI companion", size=(750, 800))
        self.window = window
        self.panel = XPSAssistantPanel(self, window)

        self._create_menu_bar()

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.panel, 1, wx.EXPAND)
        self.SetSizer(sizer)
        self.Centre()

        # Chat history storage
        self.conversation_history = []  # List of message dicts
        self.conversation_id = None  # Unique ID for this conversation

    def _create_menu_bar(self):
        menubar = wx.MenuBar()

        # Create Chat menu
        chat_menu = wx.Menu()

        save_item = chat_menu.Append(wx.ID_ANY, "Save Conversation\tCtrl+S", "Save current chat to file")
        load_item = chat_menu.Append(wx.ID_ANY, "Load Conversation\tCtrl+O", "Load chat from file")
        chat_menu.AppendSeparator()
        new_item = chat_menu.Append(wx.ID_ANY, "New Conversation\tCtrl+N", "Start new chat")
        chat_menu.AppendSeparator()
        export_item = chat_menu.Append(wx.ID_ANY, "Export as Text", "Export chat as text file")

        # Bind events - call through the panel
        self.Bind(wx.EVT_MENU, lambda e: self.panel.save_conversation(), save_item)
        self.Bind(wx.EVT_MENU, lambda e: self.panel.load_conversation(), load_item)
        self.Bind(wx.EVT_MENU, lambda e: self.panel._clear_history(), new_item)
        self.Bind(wx.EVT_MENU, lambda e: self.panel._export_as_text(), export_item)

        # Add to menubar
        menubar.Append(chat_menu, "&Chat")

        # # Mode Menu
        # mode_menu = wx.Menu()
        # self.mode_chatgpt_mini = mode_menu.AppendRadioItem(wx.ID_ANY, "gpt-4o-mini (Fast, Low Cost)")
        # self.mode_gpt4o = mode_menu.AppendRadioItem(wx.ID_ANY, "gpt-4o (More Capable)")
        # mode_menu.AppendSeparator()
        # self.mode_runpod = mode_menu.AppendRadioItem(wx.ID_ANY, "RunPod (Custom LLM)")
        # self.mode_runpod.Enable(False)
        # menubar.Append(mode_menu, "&Mode")

        model_menu = self.create_model_menu()
        menubar.Append(model_menu, "Model")

        # Edit Menu
        edit_menu = wx.Menu()
        config_item = edit_menu.Append(wx.ID_PREFERENCES, "Configuration...\tCtrl+,")
        edit_menu.AppendSeparator()
        clear_chat_item = edit_menu.Append(wx.ID_ANY, "Clear Chat")
        menubar.Append(edit_menu, "&Edit")

        # Help Menu
        help_menu = wx.Menu()
        about_item = help_menu.Append(wx.ID_ABOUT, "About")
        help_menu.AppendSeparator()
        openai_key_item = help_menu.Append(wx.ID_ANY, "Get OpenAI API Key...")
        menubar.Append(help_menu, "&Help")

        self.SetMenuBar(menubar)

        # Bind events
        # self.Bind(wx.EVT_MENU, self.on_mode_changed, self.mode_chatgpt_mini)
        # self.Bind(wx.EVT_MENU, self.on_mode_changed, self.mode_gpt4o)
        # self.Bind(wx.EVT_MENU, self.on_mode_changed, self.mode_runpod)
        self.Bind(wx.EVT_MENU, self.panel.on_config, config_item)
        self.Bind(wx.EVT_MENU, self.panel.on_clear_chat, clear_chat_item)
        self.Bind(wx.EVT_MENU, self.on_about, about_item)
        self.Bind(wx.EVT_MENU, lambda e: wx.LaunchDefaultBrowser(
            "https://platform.openai.com/api-keys"), openai_key_item)

        # # Set initial mode
        # if self.panel.model == "gpt-4o-mini":
        #     self.mode_chatgpt_mini.Check(True)
        # else:
        #     self.mode_gpt4o.Check(True)

    def get_available_models(self):
        """Return static list of available GPT models"""
        self.model_load_status = "Using standard model list"
        return [
            "gpt-5.2",
            "gpt-5.1",
            "gpt-5",
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-4",
            "gpt-3.5-turbo",
            "o1",
            "o1-mini",
            "o3",
            "o3-mini"
        ]
    def get_available_models_OLD(self):
        """Fetch available GPT models from OpenAI API"""
        try:
            import openai
            api_key = getattr(self, 'api_key', None)
            if hasattr(self, 'panel') and hasattr(self.panel, 'api_key'):
                api_key = self.panel.api_key

            if not api_key:
                self.model_load_status = "⚠ No API key - using default list"
                return self.get_default_models()

            client = openai.OpenAI(api_key=api_key)
            models = client.models.list()

            # Filter for standard chat models only
            gpt_models = []
            for m in models.data:
                model_id = m.id

                # Skip specialized models
                if any(x in model_id for x in [
                    '-instruct', '-embedding', '-audio', '-realtime', '-search',
                    '-tts', '-whisper', '-transcribe', '-codex', '-pro', '-preview',
                    '-mini-tts', '-mini-audio', '-mini-search', '-mini-realtime',
                    '-mini-transcribe', '-chat-latest', '-codex-mini', '-codex-max',
                    '-search-api', '-nano'
                ]):
                    continue

                # Include only main chat models
                if model_id in ['gpt-5.2', 'gpt-5.1', 'gpt-5', 'gpt-5-mini',
                                'gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-4',
                                'gpt-3.5-turbo', 'o1', 'o1-mini', 'o3', 'o3-mini']:
                    gpt_models.append(model_id)

            gpt_models.sort(reverse=True)

            if gpt_models:
                self.model_load_status = f"✓ Loaded {len(gpt_models)} standard models"
                return gpt_models
            else:
                self.model_load_status = "⚠ No standard models found - using default list"
                return self.get_default_models()

        except Exception as e:
            self.model_load_status = f"✗ API failed: {str(e)[:50]}"
            print(f"Error fetching models: {e}")
            return self.get_default_models()
    def get_default_models(self):
        """Default model list if API call fails"""
        return [
            "gpt-5.2",
            "gpt-5.1",
            "gpt-5",
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-4",
            "gpt-3.5-turbo",
            "o1",
            "o1-mini",
            "o3",
            "o3-mini"
        ]

    def create_model_menu(self):
        """Create model menu dynamically from available models"""
        model_menu = wx.Menu()

        # Get available models
        available_models = self.get_available_models()

        # Create menu items for each model
        self.model_menu_items = {}
        for model_name in available_models:
            item = model_menu.Append(wx.ID_ANY, model_name, kind=wx.ITEM_RADIO)
            self.Bind(wx.EVT_MENU, lambda e, m=model_name: self.set_model(m), item)
            self.model_menu_items[model_name] = item

            # Check current model (get from panel if exists)
            current_model = getattr(self.panel, 'model', 'gpt-4o') if hasattr(self, 'panel') else 'gpt-4o'
            if model_name == current_model:
                item.Check(True)

        return model_menu

    def set_model(self, model_name):
        """Set the current model"""
        if hasattr(self, 'panel'):
            self.panel.model = model_name
            self.panel._save_config()

    def on_about(self, event):
        wx.MessageBox(
            "XPS Assistant for KherveFitting\n\n"
            "AI-powered peak identification and fitting advice.\n\n"
            "Select model from Mode menu:\n"
            "• gpt-4o-mini: Fast, low cost\n"
            "• gpt-4o: More capable\n\n"
            "Element documentation is sent once per element.\n"
            "The AI remembers your conversation.\n\n"
            "Gwilherm Kerherve - KherveFitting",
            "About", wx.OK | wx.ICON_INFORMATION)


class XPSAssistantPanel(wx.Panel):
    """Simplified XPS Assistant Panel with chat interface"""

    # Config saved to ~/.khervefitting/chatgpt_config.json (same as before)
    CONFIG_PATH = os.path.expanduser("~/.khervefitting/chatgpt_config.json")

    # Element docs are in the installation folder: libraries/LLMs/element_docs/
    DOCS_PATH = os.path.join(os.path.dirname(__file__), 'element_docs')

    def __init__(self, parent, window):
        super().__init__(parent)
        self.window = window
        self.api_key = ""
        self.model = "gpt-4o"
        self.conversation_history = []
        self.element_context_sent = {}
        self.suggested_peaks = []
        self.chat_html = ""  # HTML content for chat bubbles

        self.current_technique = "XPS"  # Default technique
        self.auto_fit_loop_count = 2  # Default loop count
        self.response_verbosity = "Concise"  # Default verbosity
        self.send_images = False  # Default: don't send images
        self.temperature = 0.3  # Default temperature
        self.max_tokens = 4000  # Default max tokens
        self.locked_bg_low = None  # User-set low BE background (don't change)
        self.locked_bg_high = None  # User-set high BE background (don't change)

        self._load_config()
        self._load_prompts()
        self._create_ui()
        self._populate_data()

    def _create_ui(self):
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Set dark background on panel
        self.SetBackgroundColour(wx.Colour(105, 105, 128))

        # Top Row: Core Level + Action Buttons
        top_row_panel = wx.Panel(self, style=wx.BORDER_SIMPLE)
        top_row = wx.BoxSizer(wx.HORIZONTAL)

        lbl = wx.StaticText(top_row_panel, label="Data:")
        lbl.SetForegroundColour(wx.Colour(250, 250, 250))
        top_row.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)

        self.data_combo = wx.ComboBox(top_row_panel, style=wx.CB_READONLY | wx.EXPAND, size=(80, -1))
        self.data_combo.Bind(wx.EVT_COMBOBOX, self.on_data_changed)
        top_row.Add(self.data_combo, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 2)

        refresh_btn = wx.Button(top_row_panel, label="↻", size=(25, 25))
        refresh_btn.SetToolTip("Refresh core levels")
        refresh_btn.Bind(wx.EVT_BUTTON, lambda e: self._populate_data())
        top_row.Add(refresh_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 15)

        # Action buttons with fixed height and gray background
        btn_colour = wx.Colour(70, 70, 95)
        text_colour = wx.Colour(220, 220, 220)



        self.identify_btn = wx.Button(top_row_panel, label="Identify\nPeaks", size=(-1, 50))
        self.identify_btn.SetBackgroundColour(btn_colour)
        self.identify_btn.SetForegroundColour(text_colour)
        self.identify_btn.Bind(wx.EVT_BUTTON, self.on_identify)
        top_row.Add(self.identify_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)

        self.suggest_btn = wx.Button(top_row_panel, label="Suggest\nFitting", size=(-1, 50))
        self.suggest_btn.SetBackgroundColour(btn_colour)
        self.suggest_btn.SetForegroundColour(text_colour)
        self.suggest_btn.Bind(wx.EVT_BUTTON, self.on_suggest_fitting)
        top_row.Add(self.suggest_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 2)

        self.apply_btn = wx.Button(top_row_panel, label="Apply Fit", size=(-1, 50))
        self.apply_btn.SetBackgroundColour(btn_colour)
        self.apply_btn.SetForegroundColour(text_colour)
        self.apply_btn.Bind(wx.EVT_BUTTON, self.on_apply_fitting)
        self.apply_btn.Enable(False)
        top_row.Add(self.apply_btn, 0, wx.ALIGN_CENTER_VERTICAL)

        # Auto Fit button - combines suggest + apply with chat confirmation
        self.auto_fit_btn = wx.Button(top_row_panel, label="Auto\nFit", size=(-1, 50))
        self.auto_fit_btn.SetBackgroundColour(btn_colour)
        self.auto_fit_btn.SetForegroundColour(text_colour)
        self.auto_fit_btn.Bind(wx.EVT_BUTTON, self.on_auto_fit)
        top_row.Add(self.auto_fit_btn, 0, wx.ALIGN_CENTER_VERTICAL)

        top_row_panel.SetSizer(top_row)
        main_sizer.Add(top_row_panel, 0, wx.EXPAND | wx.ALL, 0)

        # Chat Display - using RichTextCtrl for streaming and styling
        self.chat_display = wx.richtext.RichTextCtrl(
            self, style=wx.VSCROLL | wx.HSCROLL | wx.richtext.RE_READONLY | wx.BORDER_RAISED,
            size=(-1, 280)
        )
        # After creating chat_display
        font = wx.Font(10, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, faceName="Consolas")
        self.chat_display.SetFont(font)

        self.chat_display.SetBackgroundColour(wx.Colour(255, 255, 255))
        main_sizer.Add(self.chat_display, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 0)

        # Input Row - 2 lines multiline
        input_row = wx.BoxSizer(wx.HORIZONTAL)
        self.question_ctrl = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_PROCESS_ENTER, size=(-1, 50))
        self.question_ctrl.SetHint("Ask any question...")
        font = self.question_ctrl.GetFont()
        font.PointSize += 2
        self.question_ctrl.SetFont(font)
        self.question_ctrl.Bind(wx.EVT_TEXT_ENTER, self.on_ask)
        input_row.Add(self.question_ctrl, 1, wx.EXPAND | wx.RIGHT, 1)

        self.ask_btn = wx.Button(self, label="Ask", size=(60, 50))
        self.ask_btn.SetBackgroundColour(btn_colour)
        self.ask_btn.SetForegroundColour(text_colour)
        self.ask_btn.Bind(wx.EVT_BUTTON, self.on_ask)
        input_row.Add(self.ask_btn, 0, wx.EXPAND)

        main_sizer.Add(input_row, 0, wx.EXPAND | wx.ALL, 1)

        # Status
        self.status_label = wx.StaticText(self, label="Ready")
        self.status_label.SetForegroundColour(wx.Colour(150, 150, 150))
        main_sizer.Add(self.status_label, 0, wx.LEFT | wx.BOTTOM, 5)

        self.SetSizer(main_sizer)

        # Show welcome message after UI is created
        wx.CallAfter(self._show_welcome_message)

    def _show_welcome_message(self):
        """Display welcome message with available commands"""
        welcome_text = self._get_prompt("WELCOME_MESSAGE")

        if not welcome_text:
            # Fallback
            welcome_text = """Welcome to KherveAI! I can help you with XPS analysis.

**Just type naturally**, for example:
- "Identify the species in my spectrum"
- "Suggest a fitting for this peak"
- "Fit my data" - starts interactive fitting session

**During fitting session:**
- "yes" - apply suggested peaks and auto-analyze
- "send screenshot" - AI inspects plot for improvements
- "continue" - run more refinement iterations
- "bkg XXX YYY" - set background range manually
- "auto bkg" - automatically calculate optimal high BE background
- "done" - finish session

**Target fit quality:** RSD < 1 (good), 1-3 (acceptable)

Select a core level above and let's get started!"""

        try:
            self._append_chat("assistant", welcome_text)
        except Exception as e:
            print(f"DEBUG: Error showing welcome message: {e}")

    def _save_debug_screenshot(self, image_base64):
        """Save the screenshot to a temp file so user can verify what was sent"""
        import base64

        try:
            # Save to user's temp directory
            temp_dir = os.path.join(os.path.expanduser("~"), ".khervefitting")
            os.makedirs(temp_dir, exist_ok=True)

            screenshot_path = os.path.join(temp_dir, "last_screenshot_sent.png")

            with open(screenshot_path, 'wb') as f:
                f.write(base64.b64decode(image_base64))

            print(f"DEBUG: Screenshot saved to {screenshot_path}")
            self._append_chat("system", f"📁 Screenshot saved to: {screenshot_path}")

        except Exception as e:
            print(f"DEBUG: Could not save debug screenshot: {e}")

    def _display_screenshot_in_chat(self, image_base64):
        """Display the captured screenshot thumbnail in the chat"""
        import base64

        try:
            # Decode base64 to image
            image_data = base64.b64decode(image_base64)

            # Create wx.Image from data
            import io
            stream = io.BytesIO(image_data)
            img = wx.Image(stream, wx.BITMAP_TYPE_PNG)

            # Resize to thumbnail (max 300px wide)
            max_width = 300
            if img.GetWidth() > max_width:
                scale = max_width / img.GetWidth()
                new_height = int(img.GetHeight() * scale)
                img = img.Scale(max_width, new_height, wx.IMAGE_QUALITY_HIGH)

            bitmap = wx.Bitmap(img)

            # Insert into chat
            self.chat_display.SetInsertionPointEnd()
            self.chat_display.Newline()
            self.chat_display.WriteImage(bitmap)
            self.chat_display.Newline()
            self.chat_display.ShowPosition(self.chat_display.GetLastPosition())

        except Exception as e:
            print(f"DEBUG: Could not display screenshot in chat: {e}")

    def _identify_peaks_with_slopes(self, x_data, y_data, prominence_threshold=0.15):
        """Identify peaks considering slope changes"""
        from scipy.signal import find_peaks
        from scipy.ndimage import gaussian_filter1d

        # Smooth data moderately
        y_smooth = gaussian_filter1d(y_data, sigma=3)

        # Calculate height thresholds based on data range
        max_height = np.max(y_smooth)
        min_height = np.min(y_smooth)
        height_range = max_height - min_height

        # Find ALL peaks with very low thresholds
        all_peaks, all_props = find_peaks(y_smooth,
                                          prominence=height_range * 0.01,  # Even lower - 1%
                                          distance=10,  # Allow closer peaks
                                          width=1)

        # Keep peaks above 5% of max height (to catch satellites)
        threshold = min_height + height_range * 0.05

        filtered_peaks = []
        for idx in all_peaks:
            if y_smooth[idx] > threshold:
                filtered_peaks.append(idx)

        # Sort by binding energy (descending)
        filtered_peaks = np.array(filtered_peaks)
        filtered_peaks = filtered_peaks[np.argsort(x_data[filtered_peaks])[::-1]]

        # Calculate derivatives
        dy = np.gradient(y_smooth, x_data)
        d2y = np.gradient(dy, x_data)

        # Return peak info with labels based on position
        peak_info = []
        for idx in filtered_peaks:
            be_position = x_data[idx]

            # Determine likely assignment based on Cu 2p region
            assignment = ""
            if 930 <= be_position <= 935:
                assignment = " (likely Cu 2p3/2 - main peak)"
            elif 950 <= be_position <= 956:
                assignment = " (likely Cu 2p1/2 - main peak)"
            elif 940 <= be_position <= 948:
                assignment = " (likely shake-up satellite)"
            elif 960 <= be_position <= 968:
                assignment = " (likely satellite or plasmon)"

            peak_info.append({
                'position': float(f"{x_data[idx]:.2f}"),
                'intensity': float(f"{y_data[idx]:.2f}"),
                'slope': float(f"{dy[idx]:.2f}"),
                'curvature': float(f"{d2y[idx]:.2f}")
            })

            print(f"  Peak at {x_data[idx]:.2f} eV, intensity {y_data[idx]:.0f}{assignment}")

        print(f"DEBUG: Found {len(filtered_peaks)} peaks total")

        return peak_info

    def _load_config(self):
        if os.path.exists(self.CONFIG_PATH):
            try:
                with open(self.CONFIG_PATH, 'r') as f:
                    config = json.load(f)
                    self.api_key = config.get('api_key', '')
                    self.model = config.get('model', 'gpt-4o')
                    self.auto_fit_loop_count = config.get('loop_count', 2)
                    self.response_verbosity = config.get('verbosity', 'Concise')
                    self.send_images = config.get('send_images', False)
                    self.temperature = config.get('temperature', 0.3)
                    self.max_tokens = config.get('max_tokens', 4000)
            except:
                pass

    def _save_config(self):
        os.makedirs(os.path.dirname(self.CONFIG_PATH), exist_ok=True)
        with open(self.CONFIG_PATH, 'w') as f:
            json.dump({
                'api_key': self.api_key,
                'model': self.model,
                'loop_count': self.auto_fit_loop_count,
                'verbosity': self.response_verbosity,
                'send_images': self.send_images,
                'temperature': self.temperature,
                'max_tokens': self.max_tokens
            }, f, indent=2)

    def _load_prompts(self):
        """Load prompts from external MD file"""
        self.prompts = {}
        prompts_path = os.path.join(os.path.dirname(__file__), 'prompts.md')

        try:
            if os.path.exists(prompts_path):
                with open(prompts_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Parse sections
                current_section = None
                current_content = []

                for line in content.split('\n'):
                    if line.startswith('## '):
                        # Save previous section
                        if current_section:
                            self.prompts[current_section] = '\n'.join(current_content).strip()
                        # Start new section
                        current_section = line[3:].strip()
                        current_content = []
                    elif current_section:
                        current_content.append(line)

                # Save last section
                if current_section:
                    self.prompts[current_section] = '\n'.join(current_content).strip()

                print(f"DEBUG: Loaded {len(self.prompts)} prompts from {prompts_path}")
            else:
                print(f"DEBUG: Prompts file not found: {prompts_path}")
                self.prompts = {}

        except Exception as e:
            print(f"DEBUG: Error loading prompts: {e}")
            self.prompts = {}

    def _get_prompt(self, key, **kwargs):
        """Get a prompt by key, with optional formatting"""
        if key in self.prompts:
            try:
                return self.prompts[key].format(**kwargs)
            except KeyError as e:
                # Return unformatted if formatting fails
                return self.prompts[key]
        return ""

    def set_mode(self, model):
        if model == "runpod":
            self._update_status("RunPod not configured", "orange")
            return
        self.model = model
        self._save_config()
        self._update_status(f"Mode: {model}", "blue")

    def _populate_data(self):
        """Populate data dropdown from available sheets"""
        self.data_combo.Clear()
        try:
            if hasattr(self.window, 'Data') and 'Core levels' in self.window.Data:
                sheets = list(self.window.Data['Core levels'].keys())
                for s in sheets:
                    self.data_combo.Append(s)
                if sheets:
                    current = getattr(self.window, 'sheet_combobox', None)
                    if current and current.GetValue() in sheets:
                        self.data_combo.SetValue(current.GetValue())
                    else:
                        self.data_combo.SetSelection(0)
                    self._detect_technique()
        except Exception as e:
            print(f"Error: {e}")

    def _detect_technique(self):
        """Detect the technique from the current data"""
        sheet = self.data_combo.GetValue()
        if not sheet:
            self.current_technique = "XPS"
            return

        try:
            data = self.window.Data['Core levels'].get(sheet, {})

            # Check for technique indicators
            if 'Technique' in data:
                self.current_technique = data['Technique']
            elif any(key in sheet.lower() for key in ['eels', 'electron energy loss']):
                self.current_technique = "EELS"
            elif any(key in sheet.lower() for key in ['edx', 'eds', 'energy dispersive']):
                self.current_technique = "EDX"
            elif any(key in sheet.lower() for key in ['raman']):
                self.current_technique = "Raman"
            elif any(key in sheet.lower() for key in ['xas', 'xanes', 'exafs']):
                self.current_technique = "XAS"
            elif any(key in sheet.lower() for key in ['auger', 'aes']):
                self.current_technique = "AES"
            else:
                # Default to XPS - check for typical XPS patterns (element + orbital)
                if re.match(r'[A-Z][a-z]?\s*\d[spdf]', sheet):
                    self.current_technique = "XPS"
                else:
                    self.current_technique = "XPS"  # Default
        except:
            self.current_technique = "XPS"

    def on_data_changed(self, event):
        # Detect technique when data changes
        self._detect_technique()

    def _update_status(self, msg, color="black"):
        self.status_label.SetLabel(msg)
        colors = {"green": (0, 128, 0), "red": (200, 0, 0), "blue": (0, 0, 150),
                  "orange": (200, 100, 0), "black": (0, 0, 0)}
        self.status_label.SetForegroundColour(wx.Colour(*colors.get(color, (0, 0, 0))))

    def _append_chat(self, role, message, streaming=False):
        """Append message to chat display with styled text"""
        timestamp = datetime.datetime.now().strftime("%H:%M")

        self.chat_display.SetInsertionPointEnd()
        self.chat_display.Newline()

        if role == "user":
            # User message - green on dark green, RIGHT aligned

            # Header - right aligned
            header_style = wx.richtext.RichTextAttr()
            header_style.SetTextColour(wx.Colour(50, 100, 50))
            header_style.SetBackgroundColour(wx.Colour(240, 240, 250))
            header_style.SetFontWeight(wx.FONTWEIGHT_BOLD)
            header_style.SetFontSize(12)
            header_style.SetAlignment(wx.TEXT_ALIGNMENT_RIGHT)

            self.chat_display.BeginStyle(header_style)
            self.chat_display.WriteText(f"KherveFitting User  {timestamp}                                        ")
            self.chat_display.EndStyle()
            self.chat_display.Newline()

            # Message -
            msg_style = wx.richtext.RichTextAttr()
            msg_style.SetFontWeight(wx.FONTWEIGHT_BOLD)
            msg_style.SetTextColour(wx.Colour(0, 0, 0))
            # msg_style.SetBackgroundColour(wx.Colour(200, 200, 220))
            msg_style.SetFontSize(11)
            msg_style.SetAlignment(wx.TEXT_ALIGNMENT_RIGHT)

            self.chat_display.BeginStyle(msg_style)
            self.chat_display.WriteText(f"  {message}  ")
            self.chat_display.EndStyle()

        elif role == "system":
            # System status message - with KherveAI header and logo
            timestamp = datetime.datetime.now().strftime("%H:%M")

            # Header with logo
            header_style = wx.richtext.RichTextAttr()
            header_style.SetTextColour(wx.Colour(70, 70, 95))
            header_style.SetFontSize(12)
            header_style.SetFontWeight(wx.FONTWEIGHT_BOLD)
            header_style.SetAlignment(wx.TEXT_ALIGNMENT_LEFT)

            self.chat_display.BeginStyle(header_style)

            # Try to load and insert icon
            icon_path = os.path.join(os.path.dirname(__file__), 'khervefitting_icon.png')
            if os.path.exists(icon_path):
                try:
                    img = wx.Image(icon_path, wx.BITMAP_TYPE_PNG)
                    img.Rescale(18, 18, wx.IMAGE_QUALITY_HIGH)
                    bitmap = wx.Bitmap(img)
                    if bitmap.IsOk():
                        self.chat_display.WriteImage(bitmap)
                        self.chat_display.WriteText(f" KherveAI  {timestamp}")
                except:
                    self.chat_display.WriteText(f"KherveAI  {timestamp}")
            else:
                self.chat_display.WriteText(f"KherveAI  {timestamp}")

            self.chat_display.EndStyle()
            self.chat_display.Newline()

            # Message content
            msg_style = wx.richtext.RichTextAttr()
            msg_style.SetFontWeight(wx.FONTWEIGHT_NORMAL)
            msg_style.SetTextColour(wx.Colour(60, 60, 60))
            msg_style.SetFontSize(11)
            msg_style.SetAlignment(wx.TEXT_ALIGNMENT_LEFT)

            self.chat_display.BeginStyle(msg_style)
            self.chat_display.WriteText(f"{message}")
            self.chat_display.EndStyle()

        else:
            # KherveAI message - formatted text, LEFT aligned with icon
            header_style = wx.richtext.RichTextAttr()
            header_style.SetTextColour(wx.Colour(70, 70, 95))
            header_style.SetFontSize(12)
            header_style.SetAlignment(wx.TEXT_ALIGNMENT_LEFT)

            self.chat_display.BeginStyle(header_style)

            # Try to load and insert icon (same as _start_assistant_bubble)
            icon_path = os.path.join(os.path.dirname(__file__), 'khervefitting_icon.png')
            if os.path.exists(icon_path):
                try:
                    img = wx.Image(icon_path, wx.BITMAP_TYPE_PNG)
                    img.Rescale(18, 18, wx.IMAGE_QUALITY_HIGH)
                    bitmap = wx.Bitmap(img)
                    if bitmap.IsOk():
                        self.chat_display.WriteImage(bitmap)
                        self.chat_display.WriteText(f" KherveAI  {timestamp}")
                except:
                    self.chat_display.WriteText(f"KherveAI  {timestamp}")
            else:
                self.chat_display.WriteText(f"⚙️  KherveAI  {timestamp}")

            self.chat_display.EndStyle()
            self.chat_display.Newline()
            self._format_and_append_text(message)

        # Scroll to bottom
        self.chat_display.ShowPosition(self.chat_display.GetLastPosition())

    def _get_element_from_core_level(self, core_level):
        """Extract element from core level name like 'Cu 2p' -> 'Cu'"""
        match = re.match(r'([A-Z][a-z]?)', core_level)
        return match.group(1) if match else None

    def _load_element_documentation(self, element):
        """Load element-specific documentation file from installation folder"""
        # Primary location: libraries/LLMs/element_docs/
        doc_paths = [
            os.path.join(self.DOCS_PATH, f"{element}_DOCUMENTATION.md"),
            os.path.join(os.path.dirname(__file__), 'element_docs', f"{element}_DOCUMENTATION.md"),
            os.path.join(os.path.dirname(__file__), '..', '..', 'element_docs', f"{element}_DOCUMENTATION.md"),
            # Fallback to user folder if they add custom docs
            os.path.expanduser(f"~/.khervefitting/element_docs/{element}_DOCUMENTATION.md"),
        ]
        for path in doc_paths:
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        # Limit to first 8000 chars to avoid token limits
                        if len(content) > 8000:
                            content = content[:8000] + "\n\n[Documentation truncated...]"
                        return content
                except:
                    pass
        return None

    def _build_element_context(self, element):
        """Build context message - sent only once per element"""
        if element in self.element_context_sent:
            print(f"DEBUG: {element} documentation already sent in this session")
            return None

        doc = self._load_element_documentation(element)
        if doc:
            self.element_context_sent[element] = True
            print(f"DEBUG: Loaded {element} documentation ({len(doc)} chars)")
            return f"=== {element} XPS Reference ===\n\n{doc}"
        else:
            print(f"DEBUG: No documentation found for {element}")
        return None

    def _get_spectrum_data(self):
        """Get current spectrum data"""
        sheet = self.data_combo.GetValue()
        if not sheet:
            return None, None, None

        peaks = []
        summary = ""
        try:
            data = self.window.Data['Core levels'].get(sheet, {})

            x = None
            for k in ['B.E.', 'BE', 'Binding Energy']:
                if k in data:
                    x = data[k]
                    break
            if x is not None:
                summary = f"BE range: {min(x):.2f} - {max(x):.2f} eV"

            if 'Fitting' in data and 'Peaks' in data['Fitting']:
                for label, p in data['Fitting']['Peaks'].items():
                    peaks.append({
                        'name': label,
                        'position': float(f"{p.get('Position', 0):.2f}"),
                        'fwhm': float(f"{p.get('FWHM', 0):.2f}"),
                        'area': float(f"{p.get('Area', 0):.2f}")
                    })
        except Exception as e:
            print(f"Error: {e}")

        return sheet, peaks, summary

    def _get_raw_spectrum_from_sheet(self, sheet_name):
        """Get raw x,y data from the specified sheet"""
        try:
            data = self.window.Data['Core levels'].get(sheet_name, {})

            # Get x data (binding energy)
            x = None
            for k in ['B.E.', 'BE', 'Binding Energy']:
                if k in data:
                    x = data[k]
                    break

            # Get y data (intensity)
            y = None
            for k in ['Raw Data', 'raw', 'Raw', 'Intensity', 'intensity', 'cps', 'CPS']:
                if k in data:
                    y = data[k]
                    break

            if x is not None and y is not None:
                return np.array(x), np.array(y)

            return None, None
        except Exception as e:
            print(f"Error getting raw spectrum: {e}")
            return None, None

    def on_identify(self, event):
        """Identify peaks in current spectrum by detecting local maxima and shoulders"""
        sheet, peaks, summary = self._get_spectrum_data()
        if not sheet:
            wx.MessageBox("Select a core level", "No Data", wx.OK)
            return

        element = self._get_element_from_core_level(sheet)

        # Get raw spectrum data
        x_data, y_data = self._get_raw_spectrum_from_sheet(sheet)

        if x_data is not None and y_data is not None:
            from scipy.signal import find_peaks, savgol_filter
            from scipy.ndimage import gaussian_filter1d

            # Smooth the data
            y_smooth = gaussian_filter1d(y_data, sigma=2)

            # Calculate derivatives for shoulder detection
            # First derivative (slope)
            dy = np.gradient(y_smooth, x_data)
            # Second derivative (curvature) - negative peaks indicate peak centers
            d2y = np.gradient(dy, x_data)
            d2y_smooth = gaussian_filter1d(d2y, sigma=2)

            # Method 1: Standard peak detection (main peaks only)
            y_range = np.max(y_smooth) - np.min(y_smooth)
            prominence_threshold = y_range * 0.08  # Increased from 0.05

            peak_indices, properties = find_peaks(
                y_smooth,
                prominence=prominence_threshold,
                distance=10,  # Increased minimum distance
                width=3
            )

            # Method 2: Second derivative for shoulders (more restrictive)
            d2y_inverted = -d2y_smooth
            d2y_range = np.max(d2y_inverted) - np.min(d2y_inverted)

            d2_peak_indices, d2_properties = find_peaks(
                d2y_inverted,
                prominence=d2y_range * 0.10,  # Increased from 0.03
                distance=8,  # Increased from 3
                width=2
            )

            # Combine both methods - use standard peaks plus shoulders from 2nd derivative
            all_peak_positions = set()
            detected_peaks = []

            # Add standard peaks
            for idx in peak_indices:
                be = float(f"{x_data[idx]:.2f}")
                intensity = float(f"{y_data[idx]:.2f}")
                all_peak_positions.add(round(be, 1))
                detected_peaks.append({
                    'position': be,
                    'intensity': intensity,
                    'type': 'main peak'
                })

            # Add shoulders/overlapping peaks from second derivative
            # Much more restrictive - only clear shoulders
            for idx in d2_peak_indices:
                be = float(f"{x_data[idx]:.2f}")
                # Check if this is near an existing peak (within 1.5 eV)
                is_new = all(abs(be - existing) > 1.5 for existing in all_peak_positions)
                # Must have significant intensity (20% of range)
                intensity = float(f"{y_data[idx]:.2f}")
                baseline = np.min(y_smooth)
                is_significant = (intensity - baseline) > (y_range * 0.20)

                if is_new and is_significant:
                    all_peak_positions.add(round(be, 1))
                    detected_peaks.append({
                        'position': be,
                        'intensity': intensity,
                        'type': 'shoulder/overlap'
                    })

            # Method 3: If too many peaks detected, use stricter criteria
            if len(detected_peaks) > 8:
                detected_peaks = []
                all_peak_positions = set()

                # Stricter peak detection - only major features
                strict_prominence = y_range * 0.15  # 15% of range minimum
                strict_peak_indices, _ = find_peaks(
                    y_smooth,
                    prominence=strict_prominence,
                    distance=15,  # Minimum ~1.5 eV separation typically
                    width=4
                )

                for idx in strict_peak_indices:
                    be = float(f"{x_data[idx]:.2f}")
                    intensity = float(f"{y_data[idx]:.2f}")
                    all_peak_positions.add(round(be, 1))
                    detected_peaks.append({
                        'position': be,
                        'intensity': intensity,
                        'type': 'main peak'
                    })

                # Add only very clear shoulders (from 2nd derivative)
                strict_d2_threshold = d2y_range * 0.20
                strict_d2_indices, _ = find_peaks(
                    d2y_inverted,
                    prominence=strict_d2_threshold,
                    distance=12,
                    width=3
                )

                for idx in strict_d2_indices:
                    be = float(f"{x_data[idx]:.2f}")
                    is_new = all(abs(be - existing) > 2.0 for existing in all_peak_positions)
                    intensity = float(f"{y_data[idx]:.2f}")
                    baseline = np.min(y_smooth)
                    is_significant = (intensity - baseline) > (y_range * 0.25)

                    if is_new and is_significant:
                        all_peak_positions.add(round(be, 1))
                        detected_peaks.append({
                            'position': be,
                            'intensity': intensity,
                            'type': 'shoulder/overlap'
                        })

                # Sort again after Method 3
                detected_peaks.sort(key=lambda p: p['position'], reverse=True)


            # Sort by binding energy (high to low)
            detected_peaks.sort(key=lambda p: p['position'], reverse=True)

            if len(detected_peaks) > 0:
                # Analyze peak shape for asymmetry hints
                shape_info = self._analyze_peak_shape(x_data, y_smooth, peak_indices)

                data_text = f"Detected features in {sheet} spectrum:\n\n"
                for i, p in enumerate(detected_peaks, 1):
                    data_text += f"  {i}. {p['position']:.2f} eV - {p['type']} (intensity: {p['intensity']:.2f})\n"

                if shape_info:
                    data_text += f"\nPeak shape analysis:\n{shape_info}\n"

                data_text += f"\n{summary}\n"

                if peaks:
                    data_text += "\nExisting fitted peaks:\n"
                    data_text += "\n".join([
                        f"- {p['name']}: {p['position']:.2f} eV, FWHM: {p['fwhm']:.2f} eV"
                        for p in peaks
                    ])

                question = f"""Based on the detected peaks in this {sheet} XPS spectrum, identify the chemical states using the binding energy positions.

                {data_text}

                For each detected feature:
                1. Identify the most likely chemical assignment based on binding energy position only
                2. Provide a typical FWHM range for fitting guidance (note: actual FWHM depends on instrument, sample morphology, powder vs thin film, charging, etc.)
                3. Note any constraints (spin-orbit splitting, area ratios) if applicable
                4. Analyse peaks from low binding energy to high binding energy

                IMPORTANT: 
                - Only identify peaks that correspond to the detected features above
                - Do not suggest additional peaks that are not present in the data
                - If a shoulder is detected, it indicates an overlapping chemical state that needs a separate peak"""

            else:
                question = f"No clear peaks detected in {sheet}. {summary}\nWhat chemical states might be present?"

        elif peaks:
            peak_text = "\n".join([f"- {p['name']}: {p['position']:.2f} eV, FWHM: {p['fwhm']:.2f} eV"
                                   for p in peaks])
            question = f"Identify the chemical states for these {sheet} peaks:\n{peak_text}"
        else:
            question = f"What chemical states should I expect in {sheet}? {summary}"

        self._send_query(question, element, display_label=f"Identify peaks: {sheet}")

    def _analyze_peak_shape(self, x_data, y_smooth, peak_indices):
        """Analyze peak asymmetry to detect potential overlapping components"""
        if len(peak_indices) == 0:
            return ""

        shape_info = []
        for idx in peak_indices:
            be = x_data[idx]
            intensity = y_smooth[idx]
            baseline = np.min(y_smooth)
            half_height = (intensity + baseline) / 2

            # Find half-width on each side
            left_idx = idx
            right_idx = idx

            # Search left (higher BE)
            while left_idx > 0 and y_smooth[left_idx] > half_height:
                left_idx -= 1

            # Search right (lower BE)
            while right_idx < len(y_smooth) - 1 and y_smooth[right_idx] > half_height:
                right_idx += 1

            left_hw = abs(x_data[left_idx] - be)
            right_hw = abs(x_data[right_idx] - be)

            # Calculate asymmetry ratio
            if right_hw > 0.1:
                asymmetry = left_hw / right_hw
                if asymmetry > 1.3:
                    shape_info.append(f"Peak at {be:.2f} eV: asymmetric toward higher BE (possible overlapping component at higher BE)")
                elif asymmetry < 0.7:
                    shape_info.append(f"Peak at {be:.2f} eV: asymmetric toward lower BE (possible overlapping component at lower BE)")
                else:
                    fwhm = left_hw + right_hw
                    if fwhm > 2.0:  # Broader than typical single component
                        shape_info.append(f"Peak at {be:.2f} eV: broad (FWHM ~{fwhm:.2f} eV) - may contain multiple components")

        return "\n".join(shape_info) if shape_info else ""


    def on_suggest_fitting(self, event):
        """Suggest peak fitting parameters with proper constraints using element documentation"""
        sheet, peaks, summary = self._get_spectrum_data()
        if not sheet:
            wx.MessageBox("Select a core level", "No Data", wx.OK)
            return

        element = self._get_element_from_core_level(sheet)

        # Get raw spectrum data and detect peaks
        x_data, y_data = self._get_raw_spectrum_from_sheet(sheet)

        if x_data is None or y_data is None:
            wx.MessageBox("No spectrum data available", "No Data", wx.OK)
            return

        from scipy.signal import find_peaks
        from scipy.ndimage import gaussian_filter1d

        # Smooth the data
        y_smooth = gaussian_filter1d(y_data, sigma=2)

        # Calculate derivatives for shoulder detection
        dy = np.gradient(y_smooth, x_data)
        d2y = np.gradient(dy, x_data)
        d2y_smooth = gaussian_filter1d(d2y, sigma=2)

        # Method 1: Standard peak detection
        y_range = np.max(y_smooth) - np.min(y_smooth)
        prominence_threshold = y_range * 0.08

        peak_indices, properties = find_peaks(
            y_smooth,
            prominence=prominence_threshold,
            distance=10,
            width=3
        )

        # Method 2: Second derivative for shoulders
        d2y_inverted = -d2y_smooth
        d2y_range = np.max(d2y_inverted) - np.min(d2y_inverted)

        d2_peak_indices, d2_properties = find_peaks(
            d2y_inverted,
            prominence=d2y_range * 0.10,
            distance=8,
            width=2
        )

        # Collect detected peaks
        all_peak_positions = set()
        detected_peaks = []

        for idx in peak_indices:
            be = float(f"{x_data[idx]:.2f}")
            intensity = float(f"{y_data[idx]:.2f}")
            all_peak_positions.add(round(be, 1))
            detected_peaks.append({
                'position': be,
                'intensity': intensity,
                'type': 'main peak'
            })

        # Add shoulders
        for idx in d2_peak_indices:
            be = float(f"{x_data[idx]:.2f}")
            is_new = all(abs(be - existing) > 1.5 for existing in all_peak_positions)
            intensity = float(f"{y_data[idx]:.2f}")
            baseline = np.min(y_smooth)
            is_significant = (intensity - baseline) > (y_range * 0.20)

            if is_new and is_significant:
                all_peak_positions.add(round(be, 1))
                detected_peaks.append({
                    'position': be,
                    'intensity': intensity,
                    'type': 'shoulder/overlap'
                })

        # Method 3: If too many peaks, use stricter criteria
        if len(detected_peaks) > 8:
            detected_peaks = []
            all_peak_positions = set()

            strict_prominence = y_range * 0.15
            strict_peak_indices, _ = find_peaks(
                y_smooth,
                prominence=strict_prominence,
                distance=15,
                width=4
            )

            for idx in strict_peak_indices:
                be = float(f"{x_data[idx]:.2f}")
                intensity = float(f"{y_data[idx]:.2f}")
                all_peak_positions.add(round(be, 1))
                detected_peaks.append({
                    'position': be,
                    'intensity': intensity,
                    'type': 'main peak'
                })

            strict_d2_threshold = d2y_range * 0.20
            strict_d2_indices, _ = find_peaks(
                d2y_inverted,
                prominence=strict_d2_threshold,
                distance=12,
                width=3
            )

            for idx in strict_d2_indices:
                be = float(f"{x_data[idx]:.2f}")
                is_new = all(abs(be - existing) > 2.0 for existing in all_peak_positions)
                intensity = float(f"{y_data[idx]:.2f}")
                baseline = np.min(y_smooth)
                is_significant = (intensity - baseline) > (y_range * 0.25)

                if is_new and is_significant:
                    all_peak_positions.add(round(be, 1))
                    detected_peaks.append({
                        'position': be,
                        'intensity': intensity,
                        'type': 'shoulder/overlap'
                    })

        # Sort by binding energy (high to low)
        detected_peaks.sort(key=lambda p: p['position'], reverse=True)

        if len(detected_peaks) == 0:
            wx.MessageBox("No peaks detected in spectrum", "No Peaks", wx.OK)
            return

        # Find main peak (highest intensity)
        main_peak = max(detected_peaks, key=lambda p: p['intensity'])

        # Build detected peaks summary
        data_text = f"DETECTED PEAKS in {sheet} spectrum:\n"
        for i, p in enumerate(detected_peaks, 1):
            data_text += f"  {i}. {p['position']:.2f} eV ({p['type']}, intensity: {p['intensity']:.2f})\n"
        data_text += f"\nSpectrum range: {summary}\n"

        question = f"""Create a peak fitting model for this {sheet} XPS spectrum.

        {data_text}

        **MAIN PEAK POSITION: {main_peak['position']:.2f} eV**

        CRITICAL INSTRUCTIONS:
        1. **LOOK AT THE {element} DOCUMENTATION** - It contains multiple "Fitting Protocol" tables for different chemical states
        2. **MATCH THE MAIN PEAK POSITION ({main_peak['position']:.2f} eV)** to the reference binding energies in the documentation
        3. **SELECT THE FITTING PROTOCOL** whose reference position is closest to {main_peak['position']:.2f} eV
        4. **COPY THE EXACT TABLE** from that protocol - use all peaks, constraints, and line shapes specified
        5. Adjust Peak A position to match the detected value ({main_peak['position']:.2f} eV)

        BACKGROUND RANGE - VERY IMPORTANT:
        - Look for the "## Background Fitting" section in the {element} DOCUMENTATION
        - Find the "**Range**:" line which specifies the recommended eV range (e.g., "**Range**: Typically 280-295 eV")
        - Extract those exact values and report them as: "Background Range: XXX.XX - YYY.YY eV"
        - If no specific range is given, take the minimum BE value and for the High BE decide where the peaks finishes and add 1 eV

        PEAK LABEL FORMAT:
        - Format: "CoreLevel Species" e.g., "Sr3d5/2 Sr-O", "C1s C-C", "Cu2p3/2 CuO"
        - No space between element and orbital: "Sr3d5/2" not "Sr 3d5/2"
        - For doublet partners (2p1/2, 3d3/2, 4f5/2): use underscore to hide from legend, e.g., "Sr3d3/2_Sr-O", "Cu2p1/2_CuO"
        - Always include the chemical species after the core level

        CONSTRAINT FORMAT (KherveFitting syntax):
        - Position: "A+XX.XX#0.2" = Peak A + offset ±0.2 eV, or "XXX.XX,XXX.XX" for min,max range
        - Area: "A*0.667#0.01" = Peak A × ratio ±tolerance, or "1:1e7" for free range
        - FWHM: "A*1#0.1" = linked to Peak A ±tolerance, or "0.3:3.5" for range
        - L/G: "A*1" to link, "Fixed" to lock, or "15:80" for range
        - For s orbitals (1s): Do not constrain Area unless specified in documentation
        - To fix a value, write "Fixed" in the constraint row of any of the column like Position, FWHM, L/G, Area

        FITTING DEFAULTS:
        - Model: "SGL (Area)" for symmetric peaks, "LA (Area, σ, γ)" for asymmetric/metallic peaks
        - Background: Active Shirley
        - L/G: typically 10-30%

        OUTPUT FORMAT:
        1. First provide the background range:
           Background Range: XXX.XX - YYY.YY eV

        2. Then provide the peak table where each peak has TWO rows (values row + constraints row):
        ```
        | ID | Label           | Position      | FWHM       | L/G   | Area   | Model      |
        |----|-----------------|---------------|------------|-------|--------|------------|
        | A  | Ti2p3/2 Ti4+    | XXX.XX        | X.XX       | XX    | ---    | SGL (Area) |
        |    |                 | XXX,XXX       | 0.8:2.5    | 15:40 | 1:1e7  |            |
        | B  | Ti2p1/2_Ti4+    | XXX.XX        | X.XX       | XX    | ---    | SGL (Area) |
        |    |                 | A+X.X#0.2     | A*1        | A*1   | A*0.5  |            |
        ```
        When showing peak tables, use fixed-width monospace formatting with aligned columns. Use spaces to align columns (not tabs).

        IMPORTANT:
        - **USE THE FITTING PROTOCOL FROM DOCUMENTATION** that best matches the main peak position
        - Include ALL peaks from that protocol (even if overlapping in the spectrum)
        - Use "---" for Area values in peak rows (calculated during fitting)
        - For doublets (p, d, f orbitals): use spin-orbit splitting and area ratios from documentation
        - For s orbitals: use chemical shift constraints from documentation"""

        # Force reload element documentation for suggest fitting (ensure it's always sent)
        if element and element in self.element_context_sent:
            del self.element_context_sent[element]

        self._send_query(question, element, parse_peaks=True, display_label=f"Suggest fitting: {sheet}")

    def on_apply_fitting(self, event):
        """Apply suggested peaks with Active Shirley background"""
        if not self.suggested_peaks:
            wx.MessageBox("No peaks to apply. Use 'Suggest Fitting' first.", "No Peaks", wx.OK | wx.ICON_WARNING)
            return

        sheet = self.data_combo.GetValue()
        if not sheet:
            wx.MessageBox("No core level selected", "Error", wx.OK | wx.ICON_ERROR)
            return

        try:
            from libraries.FileMenu.Save import save_state
            save_state(self.window)

            # Get the data for this sheet
            if sheet not in self.window.Data['Core levels']:
                wx.MessageBox(f"Core level {sheet} not found", "Error", wx.OK | wx.ICON_ERROR)
                return

            core_data = self.window.Data['Core levels'][sheet]
            x_values = np.array(core_data.get('B.E.', core_data.get('BE', [])))
            y_values = np.array(core_data.get('Raw Data', []))

            if len(x_values) == 0 or len(y_values) == 0:
                wx.MessageBox("No spectrum data available", "Error", wx.OK | wx.ICON_ERROR)
                return

            # Get background range from AI suggestion or use defaults
            if hasattr(self, 'suggested_bg_range') and self.suggested_bg_range:
                bg_low = float(f"{self.suggested_bg_range['low']:.2f}")
                bg_high = float(f"{self.suggested_bg_range['high']:.2f}")
            else:
                # Fallback: estimate from peak positions with margin
                if self.suggested_peaks:
                    positions = [p['position'] for p in self.suggested_peaks]
                    bg_low = float(f"{min(positions) - 5:.2f}")
                    bg_high = float(f"{max(positions) + 5:.2f}")
                else:
                    bg_low = float(f"{min(x_values) + 1:.2f}")
                    bg_high = float(f"{max(x_values) - 1:.2f}")

            # Step 1: Create Active Shirley background with proper region
            self._create_background_region(sheet, x_values, y_values, bg_low, bg_high)

            # Step 2: Clear existing peaks from grid
            if hasattr(self.window, 'peak_params_grid'):
                num_rows = self.window.peak_params_grid.GetNumberRows()
                if num_rows > 0:
                    self.window.peak_params_grid.DeleteRows(0, num_rows)
                self.window.peak_count = 0

            # Step 3: Initialize Fitting structure
            if 'Fitting' not in core_data:
                core_data['Fitting'] = {}
            core_data['Fitting']['Peaks'] = {}

            # Step 4: Add peaks to grid and Data structure
            for i, peak in enumerate(self.suggested_peaks):
                # Get intensity at peak position from spectrum
                peak_position = peak['position']
                # Find closest x value to peak position
                idx = np.argmin(np.abs(x_values - peak_position))
                intensity_at_peak = float(y_values[idx])

                # Get background value at this position (use simple baseline estimate)
                bg_estimate = float(np.min(y_values))
                estimated_height = float(f"{max(intensity_at_peak - bg_estimate, 100.0):.2f}")
                peak['estimated_height'] = estimated_height

                self._add_peak_to_grid(peak, i, bg_low, bg_high)

                # Format label - ensure proper format
                label = peak.get('label', f"Peak {i + 1}")
                # Remove spaces between core level and orbital (e.g., "Sr 3d5/2" -> "Sr3d5/2")
                label = re.sub(r'(\w+)\s+(\d+[spdf]\d*/?\d*)', r'\1\2', label)

                # Get constraint values
                constraints = peak.get('constraints', {})
                pos_constraint = constraints.get('position', f"{peak['position'] - 2:.2f}:{peak['position'] + 2:.2f}")
                fwhm_constraint = constraints.get('fwhm', "0.3:3.5")
                lg_constraint = constraints.get('lg', "5:80")
                area_constraint = constraints.get('area', "1:1e7")

                core_data['Fitting']['Peaks'][label] = {
                    'Position': float(f"{peak['position']:.2f}"),
                    'Height': estimated_height,
                    'FWHM': float(f"{peak['fwhm']:.2f}"),
                    'L/G': float(f"{peak.get('lg', 20.0):.2f}"),
                    'Area': 1000.0,
                    'Sigma': 1.2 if 'LA' in peak.get('model', '') else 0.0,
                    'Gamma': 1.4 if 'LA' in peak.get('model', '') else 0.0,
                    'Skew': 0.0,
                    'Fitting Model': "LA (Area, σ, γ)" if 'LA' in peak.get('model', '') else "SGL (Area)",
                    'Bkg Type': 'Active Shirley',
                    'Bkg Low': bg_low,
                    'Bkg High': bg_high,
                    'Constraints': {
                        'Position': pos_constraint,
                        'Height': '1:1e7',
                        'FWHM': fwhm_constraint,
                        'L/G': lg_constraint,
                        'Area': area_constraint,
                        'Sigma': '0.01:10' if 'LA' in peak.get('model', '') else '0.3:3',
                        'Gamma': '0.01:10' if 'LA' in peak.get('model', '') else '0.3:3',
                        'Skew': '0.01:2'
                    }
                }

            # Step 5: Replot first
            if hasattr(self.window, 'clear_and_replot'):
                self.window.clear_and_replot()

            # Step 6: Trigger Fit N# Times if fitting_window is available
            fit_iterations = 20  # Default number of iterations for Active Shirley convergence
            if hasattr(self.window, 'fitting_window') and self.window.fitting_window:
                try:
                    # Use the fitting window's on_fit_multi method
                    # First set the number of iterations
                    if hasattr(self.window.fitting_window, 'fit_iterations_spin'):
                        self.window.fitting_window.fit_iterations_spin.SetValue(fit_iterations)

                    # Create a dummy event and call on_fit_multi
                    self.window.fitting_window.on_fit_multi(None)

                except Exception as e:
                    print(f"DEBUG: Error triggering fit: {e}")
                    # Fallback: just do a single fit
                    self._perform_initial_fit()
            else:
                # No fitting window, do manual fit
                self._perform_initial_fit()

            wx.MessageBox(f"Applied {len(self.suggested_peaks)} peaks with Active Shirley background ({bg_low:.2f} - {bg_high:.2f} eV)\nFitted {fit_iterations} iterations.", "Success", wx.OK | wx.ICON_INFORMATION)
            self.apply_btn.Enable(False)
            self.suggested_peaks = []
            self.suggested_bg_range = None

        except Exception as e:
            import traceback
            traceback.print_exc()
            wx.MessageBox(f"Error applying fitting: {e}", "Error", wx.OK | wx.ICON_ERROR)

    def _perform_initial_fit(self):
        """Perform initial fitting iterations when fitting_window is not available"""
        from Functions import fit_peaks
        from libraries.FileMenu.Save import save_state

        try:
            sheet_name = self.window.sheet_combobox.GetValue()
            if sheet_name not in self.window.Data['Core levels']:
                return

            core_data = self.window.Data['Core levels'][sheet_name]
            bg_method = core_data.get('Background', {}).get('Method', 'Active Shirley')
            use_active_shirley = (bg_method == "Active Shirley")

            # Perform 5 iterations
            for i in range(5):
                result = fit_peaks(self.window, self.window.peak_params_grid)

                # If Active Shirley, update background after each fit
                if use_active_shirley and hasattr(self.window, 'fit_results') and self.window.fit_results is not None:
                    self._update_active_shirley_background_manual()

                if hasattr(self.window, 'clear_and_replot'):
                    self.window.clear_and_replot()
                wx.Yield()

        except Exception as e:
            print(f"DEBUG: Error in _perform_initial_fit: {e}")

    def _update_active_shirley_background_manual(self):
        """Manual Active Shirley background update when fitting_window is not available"""
        from libraries.Peak_Functions import BackgroundCalculations

        try:
            sheet_name = self.window.sheet_combobox.GetValue()
            if sheet_name not in self.window.Data['Core levels']:
                return

            core_data = self.window.Data['Core levels'][sheet_name]
            x_values = np.array(core_data['B.E.'])
            y_raw = np.array(core_data['Raw Data'])

            bg_min = float(core_data['Background'].get('Bkg Low', min(x_values)))
            bg_max = float(core_data['Background'].get('Bkg High', max(x_values)))

            mask = (x_values >= bg_min) & (x_values <= bg_max)
            x_filtered = x_values[mask]
            y_raw_filtered = y_raw[mask]

            if hasattr(self.window, 'fit_results') and self.window.fit_results is not None:
                if 'result' in self.window.fit_results and self.window.fit_results['result'] is not None:
                    y_peaks_filtered = self.window.fit_results['result'].best_fit
                else:
                    return
            else:
                return

            offset_h = float(core_data['Background'].get('Bkg Offset High', 0))
            offset_l = float(core_data['Background'].get('Bkg Offset Low', 0))

            new_bg_filtered, k, const = BackgroundCalculations.calculate_active_shirley_from_peaks(
                x_filtered, y_raw_filtered, y_peaks_filtered, k=None, num_points=5,
                offset_h=offset_h, offset_l=offset_l
            )

            current_background = np.array(core_data['Background']['Bkg Y'])
            current_background[mask] = new_bg_filtered

            core_data['Background']['Bkg Y'] = current_background.tolist()
            core_data['Background']['Active_Shirley_k'] = float(f"{k:.6f}")
            core_data['Background']['Active_Shirley_const'] = float(f"{const:.2f}")
            core_data['Background']['Active_Shirley_const_base'] = float(f"{const - offset_l:.2f}")

            self.window.background = current_background

        except Exception as e:
            print(f"DEBUG: Error updating Active Shirley background: {e}")

    def _create_background_region(self, sheet, x_values, y_values, bg_low, bg_high):
        """Create Active Shirley background region like the Create Region button does"""
        from libraries.Peak_Functions import BackgroundCalculations

        # Ensure bg_low < bg_high
        if bg_low > bg_high:
            bg_low, bg_high = bg_high, bg_low

        # Clamp to spectrum range
        x_min, x_max = float(np.min(x_values)), float(np.max(x_values))
        bg_low = max(bg_low, x_min)
        bg_high = min(bg_high, x_max)

        # Set background parameters on window
        self.window.bg_min_energy = float(f"{bg_low:.2f}")
        self.window.bg_max_energy = float(f"{bg_high:.2f}")
        self.window.background_method = "Active Shirley"

        # Set offsets to 0
        self.window.offset_h = 0.0
        self.window.offset_l = 0.0

        # Initialize background in data structure
        core_data = self.window.Data['Core levels'][sheet]
        if 'Background' not in core_data:
            core_data['Background'] = {}

        # Calculate initial flat background for Active Shirley
        # This is a flat line at the low BE endpoint
        mask = (x_values >= bg_low) & (x_values <= bg_high)
        x_filtered = x_values[mask]
        y_filtered = y_values[mask]

        # Initial Active Shirley is a flat baseline at the low BE end
        initial_bg_filtered = BackgroundCalculations.calculate_active_shirley_background(
            x_filtered, y_filtered, offset_h=0.0, offset_l=0.0, num_points=5
        )

        # Create full background array (raw data outside region, flat inside)
        full_background = y_values.copy()
        full_background[mask] = initial_bg_filtered

        # Store all background data
        core_data['Background']['Bkg Y'] = full_background.tolist()
        core_data['Background']['Bkg X'] = x_values.tolist()
        core_data['Background']['Bkg Type'] = "Active Shirley"
        core_data['Background']['Bkg Low'] = float(f"{bg_low:.2f}")
        core_data['Background']['Bkg High'] = float(f"{bg_high:.2f}")
        core_data['Background']['Bkg Offset Low'] = 0.0
        core_data['Background']['Bkg Offset High'] = 0.0
        core_data['Background']['Method'] = "Active Shirley"

        # Record the range (format: offset_h, offset_l, min_range, max_range)
        recorded_range = (0.0, 0.0, float(f"{bg_low:.2f}"), float(f"{bg_high:.2f}"))
        core_data['Background']['Recorded_Ranges'] = [recorded_range]

        # Clear any existing Active Shirley k/const values (will be calculated after fitting)
        core_data['Background']['Active_Shirley_k'] = None
        core_data['Background']['Active_Shirley_const'] = None
        core_data['Background']['Active_Shirley_const_base'] = None

        # Set window.background
        self.window.background = np.array(full_background)

        # Set vlines to the background range
        if hasattr(self.window, 'vline1') and self.window.vline1 is not None:
            self.window.vline1.set_xdata([bg_high, bg_high])
        else:
            # Create vline1 if it doesn't exist
            self.window.vline1 = self.window.plot_manager.ax.axvline(bg_high, color='r', linestyle='--', alpha=0.7)

        if hasattr(self.window, 'vline2') and self.window.vline2 is not None:
            self.window.vline2.set_xdata([bg_low, bg_low])
        else:
            # Create vline2 if it doesn't exist
            self.window.vline2 = self.window.plot_manager.ax.axvline(bg_low, color='r', linestyle='--', alpha=0.7)

        # Update fitting window if open
        if hasattr(self.window, 'fitting_window') and self.window.fitting_window:
            try:
                # Update method combobox
                method_idx = self.window.fitting_window.method_combobox.FindString("Active Shirley")
                if method_idx != wx.NOT_FOUND:
                    self.window.fitting_window.method_combobox.SetSelection(method_idx)

                # Update range text controls
                self.window.fitting_window.updating_range_controls = True
                self.window.fitting_window.min_range_text.SetValue(f"{bg_low:.2f}")
                self.window.fitting_window.max_range_text.SetValue(f"{bg_high:.2f}")
                self.window.fitting_window.offset_h_text.SetValue("0.0")
                self.window.fitting_window.offset_l_text.SetValue("0.0")
                self.window.fitting_window.updating_range_controls = False

                # Update range boxes
                if hasattr(self.window.fitting_window, 'update_range_boxes'):
                    self.window.fitting_window.update_range_boxes()

                # Set active range
                if hasattr(self.window.fitting_window, 'set_active_range'):
                    self.window.fitting_window.set_active_range(0)

            except Exception as e:
                print(f"DEBUG: Error updating fitting window: {e}")

    def _create_active_shirley_background(self, sheet, x_values, y_values):
        """Create Active Shirley background for the spectrum"""
        # Set background parameters
        self.window.bg_min_energy = float(f"{min(x_values):.2f}")
        self.window.bg_max_energy = float(f"{max(x_values):.2f}")
        self.window.background_method = "Active Shirley"

        # Initialize background in data structure
        core_data = self.window.Data['Core levels'][sheet]
        if 'Background' not in core_data:
            core_data['Background'] = {}

        core_data['Background']['Bkg Type'] = "Active Shirley"
        core_data['Background']['Bkg Low'] = self.window.bg_min_energy
        core_data['Background']['Bkg High'] = self.window.bg_max_energy
        core_data['Background']['Bkg Offset Low'] = 0.0
        core_data['Background']['Bkg Offset High'] = 0.0

        # Calculate background
        if hasattr(self.window, 'plot_manager'):
            self.window.plot_manager.plot_background(self.window)

    def _add_peak_to_grid(self, peak, index, bg_low, bg_high):
        """Add a single peak to the peak parameters grid with constraints"""
        if not hasattr(self.window, 'peak_params_grid'):
            return

        grid = self.window.peak_params_grid
        self.window.peak_count += 1

        # Add two rows (peak values + constraints)
        grid.AppendRows(2)
        row = grid.GetNumberRows() - 2

        # Set up choice editor for fitting model
        if hasattr(self.window, 'add_choice_editor_to_new_row'):
            self.window.add_choice_editor_to_new_row(grid, row)

        # Peak ID (A, B, C, ...)
        peak_id = peak.get('id', chr(65 + index))
        grid.SetCellValue(row, 0, peak_id)
        grid.SetReadOnly(row, 0)

        # Label - format properly
        label = peak.get('label', f"Peak {index + 1}")
        label = re.sub(r'(\w+)\s+(\d+[spdf]\d*/?\d*)', r'\1\2', label)
        grid.SetCellValue(row, 1, label)

        # Position
        grid.SetCellValue(row, 2, f"{peak['position']:.2f}")

        # Height - use estimated value from intensity at peak position
        estimated_height = peak.get('estimated_height', 1000.0)
        grid.SetCellValue(row, 3, f"{estimated_height:.2f}")

        # FWHM
        grid.SetCellValue(row, 4, f"{peak['fwhm']:.2f}")

        # L/G ratio
        lg = peak.get('lg', 20.0)
        grid.SetCellValue(row, 5, f"{lg:.2f}")

        # Area (will be calculated)
        grid.SetCellValue(row, 6, "1000.00")

        # Sigma, Gamma, Skew (defaults)
        model = peak.get('model', 'SGL (Area)')
        if 'LA' in model:
            grid.SetCellValue(row, 7, "1.20")
            grid.SetCellValue(row, 8, "1.40")
        else:
            grid.SetCellValue(row, 7, "0.00")
            grid.SetCellValue(row, 8, "0.00")
        grid.SetCellValue(row, 9, "0.00")

        # Columns 10, 11, 12
        grid.SetCellValue(row, 10, "")
        grid.SetCellValue(row, 11, "")
        grid.SetCellValue(row, 12, "")

        # Column 13: Fitting Model
        if 'LA' in model:
            fitting_model = "LA (Area, σ, γ)"
        elif 'GL' in model and 'SGL' not in model:
            fitting_model = "GL (Area)"
        else:
            fitting_model = "SGL (Area)"
        grid.SetCellValue(row, 13, fitting_model)

        # Columns 14, 15, 16: Background info
        grid.SetCellValue(row, 14, "Active Shirley")
        grid.SetCellValue(row, 15, f"{bg_low:.2f}")
        grid.SetCellValue(row, 16, f"{bg_high:.2f}")

        # Set constraint row (row + 1)
        grid.SetReadOnly(row + 1, 0)
        constraints = peak.get('constraints', {})

        # Position constraint
        pos_constraint = constraints.get('position', f"{peak['position']-2:.2f}:{peak['position']+2:.2f}")
        grid.SetCellValue(row + 1, 2, pos_constraint)

        # Height constraint
        grid.SetCellValue(row + 1, 3, "1:1e7")

        # FWHM constraint
        fwhm_constraint = constraints.get('fwhm', "0.3:3.5")
        grid.SetCellValue(row + 1, 4, fwhm_constraint)

        # L/G constraint
        lg_constraint = constraints.get('lg', "5:80")
        grid.SetCellValue(row + 1, 5, lg_constraint)

        # Area constraint
        area_constraint = constraints.get('area', "1:1e7")
        grid.SetCellValue(row + 1, 6, area_constraint)

        # Sigma, Gamma, Skew constraints
        if 'LA' in model:
            grid.SetCellValue(row + 1, 7, "0.01:10")
            grid.SetCellValue(row + 1, 8, "0.01:10")
        else:
            grid.SetCellValue(row + 1, 7, "0.3:3")
            grid.SetCellValue(row + 1, 8, "0.3:3")
        grid.SetCellValue(row + 1, 9, "0.01:2")

        # Set constraint row background color
        for col in range(grid.GetNumberCols()):
            grid.SetCellBackgroundColour(row + 1, col, wx.Colour(200, 245, 228))

        grid.ForceRefresh()

    def on_auto_fit(self, event):
        """Auto Fit: Interactive fitting session with AI"""
        sheet = self.data_combo.GetValue()
        if not sheet:
            wx.MessageBox("Please select a core level first", "No Data", wx.OK | wx.ICON_WARNING)
            return

        if sheet not in self.window.Data.get('Core levels', {}):
            wx.MessageBox("Selected core level has no data", "No Data", wx.OK | wx.ICON_WARNING)
            return

        # Set flag to indicate we're in auto-fit mode
        self.auto_fit_mode = True

        # Clear any locked background values from previous session
        self.locked_bg_low = None
        self.locked_bg_high = None

        self.auto_fit_stage = 'active'
        self.auto_fit_iteration = 0
        self.auto_fit_max_iterations = self.auto_fit_loop_count

        self._append_chat("system", "🔄 Starting Fit session...")
        img_status = "images ON" if self.send_images else "images OFF"
        self._append_chat("system", f"⚙️ Settings: {self.auto_fit_max_iterations} loops | {self.response_verbosity} | {img_status}")
        self._append_chat("system", "💡 Commands: 'yes' to apply | 'send screenshot' | 'bkg XXX YYY' | 'auto bkg' | 'refit' | 'cancel'")

        # Run the initial suggestion
        self._run_auto_fit_suggest(sheet)

    def _run_auto_fit_suggest(self, sheet):
        """Run the suggestion phase of auto fit"""
        core_data = self.window.Data['Core levels'].get(sheet, {})
        x_values = np.array(core_data.get('B.E.', core_data.get('BE', [])))
        y_values = np.array(core_data.get('Raw Data', []))

        if len(x_values) == 0 or len(y_values) == 0:
            self._append_chat("assistant", "❌ No spectrum data available for this core level.")
            self.auto_fit_mode = False
            return

        element = self._get_element_from_core_level(sheet)
        detected_peaks = self._detect_peaks_multi_method(x_values, y_values)

        if not detected_peaks:
            self._append_chat("assistant", "❌ No peaks detected in the spectrum.")
            self.auto_fit_mode = False
            return

        main_peak = max(detected_peaks, key=lambda p: p['intensity'])

        data_text = f"Detected {len(detected_peaks)} peak(s):\n"
        for i, peak in enumerate(detected_peaks):
            marker = " ← MAIN PEAK" if peak == main_peak else ""
            data_text += f"  Peak {i + 1}: {peak['position']:.2f} eV (intensity: {peak['intensity']:.0f}){marker}\n"

        if element and element in self.element_context_sent:
            del self.element_context_sent[element]

        question = f"""Create a peak fitting model for this {sheet} XPS spectrum.

{data_text}

**MAIN PEAK POSITION: {main_peak['position']:.2f} eV**

CRITICAL INSTRUCTIONS:
1. **LOOK AT THE {element} DOCUMENTATION** - It contains multiple "Fitting Protocol" tables for different chemical states
2. **MATCH THE MAIN PEAK POSITION ({main_peak['position']:.2f} eV)** to the reference binding energies in the documentation
3. **SELECT THE FITTING PROTOCOL** whose reference position is closest to {main_peak['position']:.2f} eV
4. **COPY THE EXACT TABLE** from that protocol - use all peaks, constraints, and line shapes specified
5. Adjust Peak A position to match the detected value ({main_peak['position']:.2f} eV)

BACKGROUND RANGE - VERY IMPORTANT:
- Look for the "## Background Fitting" section in the {element} DOCUMENTATION
- Find the "**Range**:" line which specifies the recommended eV range (e.g., "**Range**: Typically 280-295 eV")
- Extract those exact values and report them as: "Background Range: XXX.XX - YYY.YY eV"
- If no specific range is given, take the minimum BE value and for the High BE decide where the peaks finishes and add 1 eV

PEAK LABEL FORMAT:
- Format: "CoreLevel Species" e.g., "Sr3d5/2 Sr-O", "C1s C-C", "Cu2p3/2 CuO"
- No space between element and orbital: "Sr3d5/2" not "Sr 3d5/2"
- For doublet partners 2p1/2, 3d3/2, 4f5/2 always use underscore between orbital and label to hide from legend, e.g.,
  "Sr3d3/2_Sr-O" or "Cu2p1/2_CuO" or "Au4f5/2_Au"
- Always include the chemical species after the core level

CONSTRAINT FORMAT (KherveFitting syntax):
- Position: "A+XX.XX#0.2" = Peak A + offset ±0.2 eV, or "XXX.XX,XXX.XX" for min,max range
- Area: "A*0.667#0.01" = Peak A × ratio ±tolerance, or "1:1e7" for free range
- FWHM: "A*1#0.1" = linked to Peak A ±tolerance, or "0.3:3.5" for range
- L/G: "A*1" to link, "Fixed" to lock, or "15:80" for range
- For s orbitals (1s): Do not constrain Area unless specified in documentation

FITTING DEFAULTS:
- Model: "SGL (Area)" for symmetric peaks, "LA (Area, σ, γ)" for asymmetric/metallic peaks
- Background: Active Shirley
- L/G: typically 10-30%

OUTPUT FORMAT:
1. First provide the background range:
   Background Range: XXX.XX - YYY.YY eV

2. Then provide the peak table where each peak has TWO rows (values row + constraints row):
| ID | Label           | Position      | FWHM       | L/G   | Area   | Model      |
|----|-----------------|---------------|------------|-------|--------|------------|
| A  | Ti2p3/2 Ti4+    | XXX.XX        | X.XX       | XX    | ---    | SGL (Area) |
|    |                 | XXX,XXX       | 0.8:2.5    | 15:40 | 1:1e7  |            |
| B  | Ti2p1/2_Ti4+    | XXX.XX        | X.XX       | XX    | ---    | SGL (Area) |
|    |                 | A+X.X#0.2     | A*1        | A*1   | A*0.5  |            |

When showing peak tables, use fixed-width monospace formatting with aligned columns. Use spaces to align columns (not tabs).

3. **AT THE END, ASK**: "Would you like me to apply this fitting? Reply 'yes' to apply, or describe what changes you'd like (e.g., 'use oxide species instead' or 'add a satellite peak')."

IMPORTANT:
- **USE THE FITTING PROTOCOL FROM DOCUMENTATION** that best matches the main peak position
- Include ALL peaks from that protocol (even if overlapping in the spectrum)
- Use "---" for Area values in peak rows (calculated during fitting)
- For doublets (p, d, f orbitals): use spin-orbit splitting and area ratios from documentation
- For s orbitals: use chemical shift constraints from documentation"""

        self._send_query(question, element, parse_peaks=True, display_label=f"Auto Fit: Analyzing {sheet}...")

    def _detect_peaks_multi_method(self, x_values, y_values):
        """Detect peaks using multiple methods (reused from on_identify logic)"""
        from scipy.signal import find_peaks
        from scipy.ndimage import gaussian_filter1d

        detected_peaks = []

        # Smooth data
        y_smooth = gaussian_filter1d(y_values, sigma=2)

        # Calculate baseline
        baseline = np.min(y_smooth)
        y_normalized = y_smooth - baseline
        max_intensity = np.max(y_normalized)

        if max_intensity <= 0:
            return detected_peaks

        # Method 1: Standard find_peaks with adaptive prominence
        prominence_threshold = max_intensity * 0.08
        distance = max(5, len(x_values) // 40)

        peaks_m1, properties_m1 = find_peaks(
            y_normalized,
            prominence=prominence_threshold,
            distance=distance,
            width=2
        )

        for idx in peaks_m1:
            detected_peaks.append({
                'position': float(x_values[idx]),
                'intensity': float(y_values[idx]),
                'method': 1
            })

        # Method 2: Second derivative for shoulders
        y_smooth2 = gaussian_filter1d(y_values, sigma=3)
        second_deriv = np.gradient(np.gradient(y_smooth2))
        second_deriv_smooth = gaussian_filter1d(second_deriv, sigma=2)

        neg_peaks, _ = find_peaks(
            -second_deriv_smooth,
            prominence=np.std(second_deriv_smooth) * 0.5,
            distance=distance
        )

        for idx in neg_peaks:
            pos = float(x_values[idx])
            if not any(abs(p['position'] - pos) < 0.5 for p in detected_peaks):
                if y_normalized[idx] > max_intensity * 0.05:
                    detected_peaks.append({
                        'position': pos,
                        'intensity': float(y_values[idx]),
                        'method': 2
                    })

        # Method 3: Lower threshold for smaller peaks
        peaks_m3, _ = find_peaks(
            y_normalized,
            prominence=max_intensity * 0.03,
            distance=distance * 2,
            width=3
        )

        for idx in peaks_m3:
            pos = float(x_values[idx])
            if not any(abs(p['position'] - pos) < 0.8 for p in detected_peaks):
                if y_normalized[idx] > max_intensity * 0.05:
                    detected_peaks.append({
                        'position': pos,
                        'intensity': float(y_values[idx]),
                        'method': 3
                    })

        # Sort by position (high to low BE)
        detected_peaks.sort(key=lambda p: p['position'], reverse=True)

        return detected_peaks

    def _check_auto_fit_response(self, user_input):
        """Check if user input is a response to auto-fit confirmation"""
        if not hasattr(self, 'auto_fit_mode') or not self.auto_fit_mode:
            return False

        if self.auto_fit_stage not in ['awaiting_confirmation', 'awaiting_residual_response', 'awaiting_additional_peaks']:
            return False

        user_lower = user_input.lower().strip()

        affirmative = ['yes', 'y', 'ok', 'okay', 'apply', 'do it', 'go ahead', 'proceed', 'sure', 'yep', 'yeah']
        if any(user_lower.startswith(a) or user_lower == a for a in affirmative):
            return 'apply'

        negative = ['no', 'n', 'cancel', 'stop', 'abort', 'nevermind', 'nope']
        if any(user_lower.startswith(n) or user_lower == n for n in negative):
            return 'cancel'

        return 'modify'

    def _handle_auto_fit_apply(self):
        """Handle the apply phase of auto fit with iterative refinement"""
        self._append_chat("system", "✅ Applying the suggested fitting...")

        try:
            self._apply_fitting_internal()

            # Increment iteration counter
            self.auto_fit_iteration += 1

            # After fitting, automatically send screenshot for analysis
            wx.CallAfter(self._auto_fit_analyze_and_refine)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self._append_chat("assistant", f"❌ Error applying fit: {str(e)}")
            self.auto_fit_mode = False

    def _auto_fit_analyze_and_refine(self):
        """Automatically analyze fit and suggest refinements"""
        current_rsd = self._get_current_rsd()

        self._append_chat("system", f"📊 Fit iteration {self.auto_fit_iteration}/{self.auto_fit_max_iterations} complete. RSD: {current_rsd:.2f}")

        # Check if we've reached max iterations or RSD is good enough
        if current_rsd < 1.0:
            self._append_chat("system", f"✅ Excellent fit achieved! RSD: {current_rsd:.2f} (target: <1)")
            self._append_chat("system", "💡 Type 'send screenshot' to verify, 'continue' for more refinement, 'refit', 'bkg XXX YYY', 'auto bkg', or 'done' to finish.")
            self.auto_fit_stage = 'awaiting_confirmation'
            return

        if self.auto_fit_iteration >= self.auto_fit_max_iterations:
            self._append_chat("system", f"🔄 Reached {self.auto_fit_max_iterations} iterations. RSD: {current_rsd:.2f}")
            self._append_chat("system", "💡 Type 'send screenshot' to inspect, 'continue' for more iterations, 'refit', 'bkg XXX YYY', 'auto bkg', or 'done' to finish.")
            self.auto_fit_stage = 'awaiting_confirmation'
            return

        # Auto-analyze based on send_images setting
        self._append_chat("system", f"🔍 Analyzing fit (iteration {self.auto_fit_iteration})...")

        if self.send_images:
            # Send screenshot for visual analysis
            wx.CallLater(500, self._send_screenshot_for_analysis)
        else:
            # Use numerical analysis only
            wx.CallLater(500, self._analyze_fit_numerically)

    def _analyze_fit_numerically(self):
        """Analyze fit using numerical data only (no screenshot)"""
        sheet = self.data_combo.GetValue()
        if not sheet:
            self.auto_fit_mode = False
            return

        element = self._get_element_from_core_level(sheet)
        current_rsd = self._get_current_rsd()
        peak_table = self._get_current_peak_table()

        # Calculate suggested background range from peaks
        suggested_bg = self._calculate_background_range_from_peaks()

        # Get current background range
        try:
            core_data = self.window.Data['Core levels'].get(sheet, {})
            bg_data = core_data.get('Background', {})
            current_bg_low = bg_data.get('Bkg Low', 0)
            current_bg_high = bg_data.get('Bkg High', 0)
        except:
            current_bg_low = 0
            current_bg_high = 0

        # Build locked background instruction
        locked_bg_instruction = ""
        if self.locked_bg_low is not None or self.locked_bg_high is not None:
            locked_bg_instruction = "\n**USER-LOCKED BACKGROUND VALUES (DO NOT CHANGE):**\n"
            if self.locked_bg_low is not None:
                locked_bg_instruction += f"- Low BE: {self.locked_bg_low:.2f} eV (LOCKED by user)\n"
            if self.locked_bg_high is not None:
                locked_bg_instruction += f"- High BE: {self.locked_bg_high:.2f} eV (LOCKED by user)\n"
            locked_bg_instruction += "You MUST use these exact values in your Background Range output.\n"

        question = f"""Analyze this {sheet} XPS fitting and suggest improvements.

**CURRENT FIT STATUS:**
- RSD: {current_rsd:.2f} (Target: <1)
- Current background range: {current_bg_low:.2f} - {current_bg_high:.2f} eV
{locked_bg_instruction}
**CURRENT PEAK TABLE:**
{peak_table}

**ANALYZE AND CHECK:**

1. **Background Range:**
   - Current: {current_bg_low:.2f} - {current_bg_high:.2f} eV
   - {"USE LOCKED VALUES ABOVE - DO NOT CHANGE" if (self.locked_bg_low or self.locked_bg_high) else "Suggested high BE (highest peak + FWHM): " + f"{suggested_bg['high']:.2f} eV"}
   - Never change the low BE unless user explicitly requested it

2. **Peak Positions:**
   - Are positions reasonable for the assigned species?
   - Should any peak be shifted slightly (±0.1-0.2 eV)?

3. **Peak FWHM**
    - If the peak FWHM has reached the max/min FWHM range change it by 0.1 to 0.2

4. **Constraints:**
   - If constrained to a peak, do not change
   - Any changes must be extremely small
   - Peak A cannot be constraint by Peak A. Keep peak A constrained to a range

5. **Missing Peaks:**
   - Do not add any peaks in the table. You can suggest in the comment but do not add it

**IF RSD > 1, provide an updated peak table with very very minor changes.**

Background Range: {self.locked_bg_low if self.locked_bg_low else current_bg_low:.2f} - {self.locked_bg_high if self.locked_bg_high else current_bg_high:.2f} eV

| ID | Label | Position | FWHM | L/G | Area | Model |
|----|-------|----------|------|-----|------|-------|

Ask: "Would you like me to apply these changes? Reply 'yes' to apply, 'bkg XXX YYY' to set background, 'auto bkg', or 'done' to finish."
"""

        self._send_query(question, element, parse_peaks=True,
                         display_label=f"🔍 Analyzing fit numerically (RSD: {current_rsd:.2f})...")

    def _calculate_background_range_from_peaks(self):
        """Calculate background range from peak positions and FWHMs"""
        sheet = self.data_combo.GetValue()
        if not sheet:
            return {'low': 0, 'high': 0}

        try:
            core_data = self.window.Data['Core levels'].get(sheet, {})
            peaks = core_data.get('Fitting', {}).get('Peaks', {})

            if not peaks:
                # Fallback to spectrum range
                x_values = core_data.get('B.E.', core_data.get('BE', []))
                if x_values:
                    return {'low': float(f"{min(x_values):.2f}"), 'high': float(f"{max(x_values):.2f}")}
                return {'low': 0, 'high': 0}

            positions = []
            fwhms = []

            for label, peak_data in peaks.items():
                pos = peak_data.get('Position', 0)
                fwhm = peak_data.get('FWHM', 1.0)
                positions.append(pos)
                fwhms.append(fwhm)

            if not positions:
                return {'low': 0, 'high': 0}

            # Find highest and lowest BE peaks
            max_pos_idx = positions.index(max(positions))
            min_pos_idx = positions.index(min(positions))

            # High BE = highest peak position + its FWHM
            bg_high = positions[max_pos_idx] + fwhms[max_pos_idx]+0.6

            # Low BE = lowest peak position - its FWHM
            bg_low = positions[min_pos_idx] - fwhms[min_pos_idx]

            return {
                'low': float(f"{bg_low:.2f}"),
                'high': float(f"{bg_high:.2f}")
            }

        except Exception as e:
            print(f"DEBUG: Error calculating background range: {e}")
            return {'low': 0, 'high': 0}

    def _offer_residual_analysis(self):
        """Offer to analyze residuals after fitting"""
        current_rsd = self._get_current_rsd()
        self._append_chat("system", f"✅ Fitting complete! RSD: {current_rsd:.2f}")
        self._append_chat("system", "💡 Commands: 'send screenshot' | 'continue' | 'bkg XXX YYY' | 'auto bkg' | 'done'")

    def _capture_plot_screenshot(self, dpi=100):
        """Capture the current plot as a low-DPI base64 image for AI analysis"""
        import io
        import base64

        try:
            # Try multiple ways to get the figure
            fig = None

            if hasattr(self.window, 'plot_manager') and self.window.plot_manager is not None:
                # Try common attribute names for matplotlib figure
                if hasattr(self.window.plot_manager, 'figure'):
                    fig = self.window.plot_manager.figure
                elif hasattr(self.window.plot_manager, 'fig'):
                    fig = self.window.plot_manager.fig
                elif hasattr(self.window.plot_manager, 'canvas'):
                    fig = self.window.plot_manager.canvas.figure
                elif hasattr(self.window.plot_manager, 'ax'):
                    fig = self.window.plot_manager.ax.figure

            # Fallback: try window.figure directly
            if fig is None and hasattr(self.window, 'figure'):
                fig = self.window.figure

            # Fallback: try window.canvas
            if fig is None and hasattr(self.window, 'canvas'):
                fig = self.window.canvas.figure

            if fig is None:
                print("DEBUG: Could not find matplotlib figure")
                return None

            # Save figure to bytes buffer at low DPI
            buf = io.BytesIO()
            fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight',
                        facecolor='white', edgecolor='none')
            buf.seek(0)

            # Encode to base64
            image_base64 = base64.b64encode(buf.read()).decode('utf-8')
            buf.close()

            return image_base64

        except Exception as e:
            print(f"DEBUG: Error capturing plot screenshot: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _get_current_peak_table(self):
        """Get the current fitted peaks as a formatted table string"""
        sheet = self.data_combo.GetValue()
        if not sheet:
            return None

        try:
            core_data = self.window.Data['Core levels'].get(sheet, {})
            if 'Fitting' not in core_data or 'Peaks' not in core_data['Fitting']:
                return None

            peaks = core_data['Fitting']['Peaks']
            if not peaks:
                return None

            # Build table header
            table = "| ID | Label | Position (eV) | FWHM (eV) | L/G (%) | Area | Model |\n"
            table += "|----|-------|---------------|-----------|---------|------|-------|\n"

            # Add each peak
            for i, (label, peak_data) in enumerate(peaks.items()):
                peak_id = chr(65 + i)  # A, B, C, ...
                position = peak_data.get('Position', 0)
                fwhm = peak_data.get('FWHM', 0)
                lg = peak_data.get('L/G', 0)
                area = peak_data.get('Area', 0)
                model = peak_data.get('Fitting Model', 'SGL (Area)')

                table += f"| {peak_id}  | {label} | {position:.2f} | {fwhm:.2f} | {lg:.2f} | {area:.2f} | {model} |\n"

                # Add constraints row if available
                constraints = peak_data.get('Constraints', {})
                if constraints:
                    pos_c = constraints.get('Position', '')
                    fwhm_c = constraints.get('FWHM', '')
                    lg_c = constraints.get('L/G', '')
                    area_c = constraints.get('Area', '')
                    table += f"|    |       | {pos_c} | {fwhm_c} | {lg_c} | {area_c} |       |\n"

            # Add background info
            bg_data = core_data.get('Background', {})
            if bg_data:
                bg_type = bg_data.get('Bkg Type', bg_data.get('Method', 'Unknown'))
                bg_low = bg_data.get('Bkg Low', 0)
                bg_high = bg_data.get('Bkg High', 0)
                table += f"\nBackground: {bg_type}, Range: {bg_low:.2f} - {bg_high:.2f} eV"

            # Add fit statistics if available
            if hasattr(self.window, 'fit_results') and self.window.fit_results:
                result = self.window.fit_results.get('result')
                if result and hasattr(result, 'chisqr'):
                    table += f"\nChi-squared: {result.chisqr:.2f}"
                if result and hasattr(result, 'redchi'):
                    table += f", Reduced Chi-sq: {result.redchi:.4f}"

            return table

        except Exception as e:
            print(f"DEBUG: Error getting peak table: {e}")
            return None

    def _send_screenshot_for_analysis(self):
        """Capture and send plot screenshot to AI for residual inspection"""
        self._append_chat("system", "📸 Capturing plot screenshot...")

        image_base64 = self._capture_plot_screenshot(dpi=100)

        if not image_base64:
            self._append_chat("assistant", "⚠️ Could not capture plot screenshot. Please check that a plot is visible.")
            return

        # Save the screenshot locally for user to verify what was sent
        self._save_debug_screenshot(image_base64)

        # Display thumbnail in chat
        self._display_screenshot_in_chat(image_base64)

        sheet = self.data_combo.GetValue()
        element = self._get_element_from_core_level(sheet) if sheet else None

        # Get current peak table
        peak_table = self._get_current_peak_table()

        # Calculate suggested background range
        suggested_bg = self._calculate_background_range_from_peaks()

        # Get current background range
        current_bg_low = 0
        current_bg_high = 0
        try:
            core_data = self.window.Data['Core levels'].get(sheet, {})
            bg_data = core_data.get('Background', {})
            current_bg_low = bg_data.get('Bkg Low', 0)
            current_bg_high = bg_data.get('Bkg High', 0)
        except:
            pass

        # Build locked background instruction
        locked_bg_instruction = ""
        if self.locked_bg_low is not None or self.locked_bg_high is not None:
            locked_bg_instruction = "\n**USER-LOCKED BACKGROUND VALUES (DO NOT CHANGE):**\n"
            if self.locked_bg_low is not None:
                locked_bg_instruction += f"- Low BE: {self.locked_bg_low:.2f} eV (LOCKED)\n"
            if self.locked_bg_high is not None:
                locked_bg_instruction += f"- High BE: {self.locked_bg_high:.2f} eV (LOCKED)\n"
            locked_bg_instruction += "You MUST use these exact values in your Background Range output.\n"

        # Determine which background values to use in output
        output_bg_low = self.locked_bg_low if self.locked_bg_low is not None else current_bg_low
        output_bg_high = self.locked_bg_high if self.locked_bg_high is not None else current_bg_high

        peak_table_section = ""
        if peak_table:
            peak_table_section = f"""

**CURRENT FITTED PEAKS:**
{peak_table}
"""

        # Get x-axis range from data
        x_range_info = ""
        try:
            core_data = self.window.Data['Core levels'].get(sheet, {})
            x_values = core_data.get('B.E.', core_data.get('BE', []))
            if len(x_values) > 0:
                x_min = min(x_values)
                x_max = max(x_values)
                x_range_info = f"\n**X-AXIS INFO:** Binding Energy range is {x_max:.2f} eV (left) to {x_min:.2f} eV (right). Higher BE is on the LEFT side."
        except:
            pass

        current_rsd = self._get_current_rsd()

        # Build the message with image for vision-capable models
        question = f"""I've attached a screenshot of my current {sheet} XPS fitting.
{peak_table_section}
{x_range_info}
{locked_bg_instruction}
**PLOT LAYOUT:**
- Top panel: XPS spectrum with raw data (black dots), fitted envelope (black line), individual peak components (colored filled areas), background (dashed line)
- Bottom panel: Residuals (cyan line) = Raw Data - Background - Fitted Peaks
- X-axis: Binding Energy in eV, **DECREASING from LEFT to RIGHT**

**FIT QUALITY METRICS:**
- Current RSD = {current_rsd:.2f}
- Target RSD < 1.00 (GOOD), 1-3 (ACCEPTABLE), >3 (NEEDS IMPROVEMENT)

**ANALYZE AND CHECK THE FOLLOWING:**

1. **RESIDUALS (Bottom Panel - MOST IMPORTANT):**
   - Is the cyan line flat and randomly scattered around zero?
   - Are there systematic bumps (positive) or dips (negative)?
   - Read the EXACT binding energy from the x-axis where deviations occur

2. **BACKGROUND RANGE:**
   - Current range: {current_bg_low:.2f} - {current_bg_high:.2f} eV
   - {"USE LOCKED VALUES ABOVE - DO NOT CHANGE" if (self.locked_bg_low or self.locked_bg_high) else "Adjust only if background doesn't meet data at edges"}
   - Only adjust the HIGH BE side if needed, never change low BE unless explicitly requested

3. **PEAK POSITIONS:**
   - Are any peaks visibly shifted from the data maximum?
   - Should any peak position be moved slightly (±0.1-0.3 eV)?
   - Check if the envelope (black line) aligns with the data points (black dots)

4. **CONSTRAINTS:**
   - Are constraints too RESTRICTIVE (peaks can't move to fit properly)?
   - Are constraints too LOOSE (peaks moved to unrealistic positions)?
   - Check FWHM constraints: typical XPS FWHM is 0.8-2.0 eV
   - Check L/G constraints: typically 15-40%

5. **MISSING PEAKS:**
   - Only suggest adding a peak if there's a CLEAR systematic bump in residuals
   - Identify the exact BE position from the x-axis

**RESPONSE FORMAT:**

If RSD > 1 or issues found, provide:
1. Specific diagnosis of what's wrong
2. Recommended adjustments (be precise with values)
3. Updated peak table with changes:

Background Range: {output_bg_low:.2f} - {output_bg_high:.2f} eV

| ID | Label | Position   | FWHM | L/G | Area | Model      |
|----|-------|------------|------|-----|------|------------|
| A  | ...   | XXX.XX     | X.XX | XX  | ---  | SGL (Area) |
|    |       | constraint | ...  | ... | ...  |            |

If fit looks GOOD (RSD < 1, flat residuals), say "✅ Fit looks good" and confirm no changes needed.

Ask: "Would you like me to apply these changes? Reply 'yes' to apply, 'bkg XXX YYY' to set background, 'auto bkg', or 'done' to finish."
"""

        # Send with image if using a vision-capable model
        self._send_query_with_image(question, image_base64, element,
                                    display_label="📸 Analyzing plot screenshot...")

    def _get_current_rsd(self):
        """Get the current RSD% from the plot - uses the same calculation as plot_operations.py"""
        try:
            sheet = self.data_combo.GetValue()
            if not sheet:
                return 0.0

            core_data = self.window.Data['Core levels'].get(sheet, {})

            # Get the values needed for RSD calculation
            y_values = np.array(core_data.get('Raw Data', []))

            # Get overall fit from window
            if hasattr(self.window, 'fit_results') and self.window.fit_results:
                result = self.window.fit_results.get('result')
                if result is not None and hasattr(result, 'best_fit'):
                    # Get background
                    background = np.array(core_data.get('Background', {}).get('Bkg Y', []))
                    x_values = np.array(core_data.get('B.E.', core_data.get('BE', [])))

                    bg_low = float(core_data.get('Background', {}).get('Bkg Low', min(x_values)))
                    bg_high = float(core_data.get('Background', {}).get('Bkg High', max(x_values)))
                    mask = (x_values >= bg_low) & (x_values <= bg_high)

                    # Build overall_fit like plot_operations does
                    overall_fit = background.copy()
                    overall_fit[mask] = background[mask] + result.best_fit

                    # Use the same function as plot_operations
                    from libraries.Peak_Functions import PeakFunctions
                    rsd_result = PeakFunctions.calculate_rsd(y_values, overall_fit)

                    if rsd_result is not None:
                        old_rsd, norm_chi, rsd_pct = rsd_result
                        return float(f"{old_rsd:.2f}")

            return 0.0

        except Exception as e:
            print(f"DEBUG: Error getting RSD: {e}")
            import traceback
            traceback.print_exc()
            return 0.0

    def _send_query_with_image(self, question, image_base64, element=None, display_label=None):
        """Send query with image to vision-capable API"""
        chat_display_text = display_label if display_label else question
        self._append_chat("user", chat_display_text)
        self._update_status("KherveAI is analyzing the plot...", "blue")
        self._enable_buttons(False)

        def run():
            try:
                self._query_api_with_image(question, image_base64, element)
            except Exception as e:
                wx.CallAfter(self._show_error, str(e))

        t = threading.Thread(target=run, daemon=True)
        t.start()

    def _query_api_with_image(self, question, image_base64, element=None):
        """Query API with image attachment for vision analysis"""
        if not self.api_key:
            wx.CallAfter(self._show_error, "No API key. Go to Edit > Configuration.")
            return

        # Check if model supports vision
        vision_models = ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-4-turbo-2024-04-09']
        model_to_use = self.model

        # Check if current model supports vision
        model_supports_vision = any(vm in self.model for vm in vision_models)

        if not model_supports_vision:
            # Switch to gpt-4o for vision capability
            model_to_use = "gpt-4o"
            wx.CallAfter(self._append_chat, "system", f"⚠️ Model '{self.model}' doesn't support images. Using 'gpt-4o' for this request.")

        messages = [{"role": "system", "content": self._build_system_prompt()}]

        # Send element context once
        if element:
            context = self._build_element_context(element)
            if context:
                messages.append({"role": "user", "content": f"[Reference]\n{context}"})
                messages.append({"role": "assistant", "content": f"Loaded {element} reference data."})

        # Add conversation history (last 4 messages to save tokens with image)
        for msg in self.conversation_history[-4:]:
            # Skip any previous image messages in history
            if isinstance(msg.get('content'), list):
                continue
            messages.append(msg)

        # Build message with image content - CORRECT FORMAT FOR OPENAI VISION API
        user_message = {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{image_base64}",
                        "detail": "high"  # Use high detail for reading axis labels
                    }
                },
                {
                    "type": "text",
                    "text": question
                }
            ]
        }

        messages.append(user_message)

        # Debug: print what we're sending
        print(f"\n{'=' * 60}")
        print(f"DEBUG: Sending image request to model: {model_to_use}")
        print(f"DEBUG: Image base64 length: {len(image_base64)} chars")
        print(f"DEBUG: Number of messages: {len(messages)}")
        print(f"{'=' * 60}\n")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": model_to_use,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": True
        }

        wx.CallAfter(self._start_assistant_bubble)

        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=data,
                timeout=120,
                stream=True
            )

            # Debug: print response status
            print(f"DEBUG: Response status code: {response.status_code}")

            if response.status_code == 400:
                error_text = response.text[:1000]
                print(f"DEBUG: 400 Error response: {error_text}")
                wx.CallAfter(self._show_error, f"API error 400 - Model may not support images.\n\nTry selecting 'gpt-4o' from the Model menu.\n\nDetails: {error_text[:200]}")
                return

            if response.status_code != 200:
                error_text = response.text[:500]
                print(f"DEBUG: Error response: {error_text}")
                wx.CallAfter(self._show_error, f"API error: {response.status_code}\n{error_text}")
                return

            full_response = ""
            for line in response.iter_lines():
                if line:
                    line_text = line.decode('utf-8')
                    if line_text.startswith('data: '):
                        json_str = line_text[6:]
                        if json_str.strip() == '[DONE]':
                            break
                        try:
                            chunk = json.loads(json_str)
                            if 'choices' in chunk and len(chunk['choices']) > 0:
                                delta = chunk['choices'][0].get('delta', {})
                                content = delta.get('content', '')
                                if content:
                                    full_response += content
                                    wx.CallAfter(self._stream_text, content)
                        except json.JSONDecodeError as e:
                            print(f"DEBUG: JSON decode error: {e}")

            if not full_response:
                wx.CallAfter(self._show_error, "No response received from API. The model may not support image input.")
                return

            # Save to history (without image to save space)
            self.conversation_history.append({
                "role": "user",
                "content": f"[Screenshot analysis request for {self.data_combo.GetValue()}]"
            })
            self.conversation_history.append({
                "role": "assistant",
                "content": full_response
            })

            wx.CallAfter(self._finish_streaming, full_response)

        except requests.exceptions.Timeout:
            wx.CallAfter(self._show_error, "Request timed out. The image may be too large.")
        except Exception as e:
            print(f"DEBUG: Exception in image query: {e}")
            import traceback
            traceback.print_exc()
            wx.CallAfter(self._show_error, str(e))

    def _apply_fitting_internal(self):
        """Internal method to apply fitting without showing message box"""
        if not self.suggested_peaks:
            raise Exception("No peaks to apply")

        sheet = self.data_combo.GetValue()
        if not sheet:
            raise Exception("No core level selected")

        from libraries.FileMenu.Save import save_state
        save_state(self.window)

        core_data = self.window.Data['Core levels'][sheet]
        x_values = np.array(core_data.get('B.E.', core_data.get('BE', [])))
        y_values = np.array(core_data.get('Raw Data', []))

        # Get background range
        if hasattr(self, 'suggested_bg_range') and self.suggested_bg_range:
            bg_low = float(f"{self.suggested_bg_range['low']:.2f}")
            bg_high = float(f"{self.suggested_bg_range['high']:.2f}")
        else:
            positions = [p['position'] for p in self.suggested_peaks]
            bg_low = float(f"{min(positions) - 5:.2f}")
            bg_high = float(f"{max(positions) + 5:.2f}")

        # Create background region
        self._create_background_region(sheet, x_values, y_values, bg_low, bg_high)

        # Clear existing peaks
        if hasattr(self.window, 'peak_params_grid'):
            num_rows = self.window.peak_params_grid.GetNumberRows()
            if num_rows > 0:
                self.window.peak_params_grid.DeleteRows(0, num_rows)
            self.window.peak_count = 0

        # Initialize Fitting structure
        if 'Fitting' not in core_data:
            core_data['Fitting'] = {}
        core_data['Fitting']['Peaks'] = {}

        # Add peaks
        for i, peak in enumerate(self.suggested_peaks):
            peak_position = peak['position']
            idx = np.argmin(np.abs(x_values - peak_position))
            intensity_at_peak = float(y_values[idx])
            bg_estimate = float(np.min(y_values))
            estimated_height = float(f"{max(intensity_at_peak - bg_estimate, 100.0):.2f}")
            peak['estimated_height'] = estimated_height

            self._add_peak_to_grid(peak, i, bg_low, bg_high)

            label = peak.get('label', f"Peak {i + 1}")
            label = re.sub(r'(\w+)\s+(\d+[spdf]\d*/?\d*)', r'\1\2', label)

            constraints = peak.get('constraints', {})
            pos_constraint = constraints.get('position', f"{peak['position'] - 2:.2f}:{peak['position'] + 2:.2f}")
            fwhm_constraint = constraints.get('fwhm', "0.3:3.5")
            lg_constraint = constraints.get('lg', "5:80")
            area_constraint = constraints.get('area', "1:1e7")

            core_data['Fitting']['Peaks'][label] = {
                'Position': float(f"{peak['position']:.2f}"),
                'Height': estimated_height,
                'FWHM': float(f"{peak['fwhm']:.2f}"),
                'L/G': float(f"{peak.get('lg', 20.0):.2f}"),
                'Area': 1000.0,
                'Sigma': 1.2 if 'LA' in peak.get('model', '') else 0.0,
                'Gamma': 1.4 if 'LA' in peak.get('model', '') else 0.0,
                'Skew': 0.0,
                'Fitting Model': "LA (Area, σ, γ)" if 'LA' in peak.get('model', '') else "SGL (Area)",
                'Bkg Type': 'Active Shirley',
                'Bkg Low': bg_low,
                'Bkg High': bg_high,
                'Constraints': {
                    'Position': pos_constraint,
                    'Height': '1:1e7',
                    'FWHM': fwhm_constraint,
                    'L/G': lg_constraint,
                    'Area': area_constraint,
                    'Sigma': '0.01:10' if 'LA' in peak.get('model', '') else '0.3:3',
                    'Gamma': '0.01:10' if 'LA' in peak.get('model', '') else '0.3:3',
                    'Skew': '0.01:2'
                }
            }

        # Replot
        if hasattr(self.window, 'clear_and_replot'):
            self.window.clear_and_replot()

        # Trigger fitting with 20 iterations
        fit_iterations = 20
        if hasattr(self.window, 'fitting_window') and self.window.fitting_window:
            try:
                if hasattr(self.window.fitting_window, 'fit_iterations_spin'):
                    self.window.fitting_window.fit_iterations_spin.SetValue(fit_iterations)
                self.window.fitting_window.on_fit_multi(None)
            except Exception as e:
                print(f"DEBUG: Error triggering fit: {e}")
                self._perform_initial_fit()
        else:
            self._perform_initial_fit()

        self._append_chat("system", f"✅ Applied {len(self.suggested_peaks)} peaks with Active Shirley background ({bg_low:.2f} - {bg_high:.2f} eV)")
        self._append_chat("system", f"🔄 Fitted {fit_iterations} iterations")

        self.suggested_peaks = []
        self.suggested_bg_range = None

    def _analyze_residuals_after_fit(self):
        """Analyze residuals after fitting to check if additional peaks are needed"""
        self.auto_fit_stage = 'analyzing'

        sheet = self.data_combo.GetValue()
        if not sheet or sheet not in self.window.Data.get('Core levels', {}):
            self.auto_fit_mode = False
            return

        try:
            core_data = self.window.Data['Core levels'][sheet]
            x_values = np.array(core_data.get('B.E.', []))
            y_values = np.array(core_data.get('Raw Data', []))
            background = np.array(core_data.get('Background', {}).get('Bkg Y', y_values))

            # Get fitted peaks sum
            if not hasattr(self.window, 'fit_results') or self.window.fit_results is None:
                self._append_chat("assistant", "⚠️ Could not analyze residuals - no fit results available.")
                self.auto_fit_mode = False
                return

            # Calculate residuals
            if 'result' in self.window.fit_results and self.window.fit_results['result'] is not None:
                fitted = self.window.fit_results['result'].best_fit

                # Get the mask for the fitted region
                bg_low = float(core_data['Background'].get('Bkg Low', min(x_values)))
                bg_high = float(core_data['Background'].get('Bkg High', max(x_values)))
                mask = (x_values >= bg_low) & (x_values <= bg_high)

                x_filtered = x_values[mask]
                y_filtered = y_values[mask]
                bg_filtered = background[mask]

                # Residuals = data - background - fitted peaks
                residuals = y_filtered - bg_filtered - fitted

                # Analyze residuals for significant peaks
                residual_peaks = self._find_residual_peaks(x_filtered, residuals, y_filtered)

                if residual_peaks:
                    # Get element for context
                    element = self._get_element_from_core_level(sheet)

                    # Build message about residual peaks
                    peaks_text = "\n".join([f"  - {p['position']:.2f} eV (residual intensity: {p['intensity']:.0f})"
                                            for p in residual_peaks])

                    question = f"""I've completed the initial fitting for {sheet}. 

Analyzing the residuals, I found {len(residual_peaks)} potential unfitted peak(s):
{peaks_text}

Based on the {element} documentation:
1. Should any additional peaks (singlet or doublet) be added to improve the fit?
2. Could these residuals indicate:
   - A different chemical species that should be included?
   - Satellite peaks (shake-up, plasmon loss)?
   - Asymmetry that requires a different line shape?

Please suggest if and what peaks should be added, or confirm the fit is complete.
Reply with 'done' if the fit looks good, or describe what peaks to add."""

                    self._send_query(question, element, parse_peaks=False,
                                     display_label="Analyzing residuals for additional peaks...")
                    self.auto_fit_stage = 'awaiting_residual_response'
                else:
                    self._append_chat("assistant", "✅ Fit complete! Residuals look clean - no significant unfitted peaks detected.")
                    self.auto_fit_mode = False
            else:
                self._append_chat("assistant", "⚠️ Could not analyze residuals - fit results not in expected format.")
                self.auto_fit_mode = False

        except Exception as e:
            print(f"DEBUG: Error analyzing residuals: {e}")
            self._append_chat("assistant", f"⚠️ Error analyzing residuals: {str(e)}")
            self.auto_fit_mode = False

    def _find_residual_peaks(self, x_values, residuals, original_y):
        """Find significant peaks in residuals that might need additional fitting"""
        from scipy.signal import find_peaks
        from scipy.ndimage import gaussian_filter1d

        residual_peaks = []

        # Smooth residuals
        residuals_smooth = gaussian_filter1d(residuals, sigma=2)

        # Calculate noise level from residuals
        noise_std = np.std(residuals_smooth)

        # Only look for peaks significantly above noise (3 sigma)
        threshold = 3 * noise_std

        # Also check relative to original signal
        original_max = np.max(original_y) - np.min(original_y)
        min_peak_height = original_max * 0.03  # At least 3% of original signal

        # Find peaks in residuals
        peaks, properties = find_peaks(
            residuals_smooth,
            height=max(threshold, min_peak_height),
            prominence=noise_std * 2,
            distance=max(3, len(x_values) // 30)
        )

        for idx in peaks:
            if residuals_smooth[idx] > threshold and residuals_smooth[idx] > min_peak_height:
                residual_peaks.append({
                    'position': float(x_values[idx]),
                    'intensity': float(residuals_smooth[idx])
                })

        # Sort by intensity (largest first)
        residual_peaks.sort(key=lambda p: p['intensity'], reverse=True)

        # Return top 3 at most
        return residual_peaks[:3]

    def on_ask(self, event):
        """Handle ask button and send message"""

        # Load knowledge base ONCE at start of chat (like element docs)
        if not self.conversation_history:  # Only on first message
            kb_message = self._load_knowledge_base_for_chat()
            self.conversation_history.append({
                "role": "user",
                "content": kb_message
            })
            self.conversation_history.append({
                "role": "assistant",
                "content": "Knowledge base loaded. Ready to help with XPS analysis."
            })

        question = self.question_ctrl.GetValue().strip()
        if not question:
            return

        self.question_ctrl.Clear()

        # Check if this is a response in auto-fit mode
        if hasattr(self, 'auto_fit_mode') and self.auto_fit_mode:
            user_lower = question.lower().strip()

            # Check for loops command (e.g., "loops 3" or "set loops 5")
            loops_match = re.search(r'loops?\s*(\d+)', user_lower)
            if loops_match:
                new_loops = int(loops_match.group(1))
                new_loops = max(1, min(10, new_loops))  # Clamp between 1-10
                self.auto_fit_loop_count = new_loops
                self.auto_fit_max_iterations = new_loops
                self._append_chat("user", question)
                self._append_chat("system", f"🔄 Set refinement loops to {new_loops}")
                return

            # Check for continue command
            if user_lower in ['continue', 'more', 'refine', 'keep going']:
                self._append_chat("user", question)
                self.auto_fit_iteration = 0  # Reset counter
                self._append_chat("system", f"🔄 Continuing refinement for {self.auto_fit_max_iterations} more iterations...")
                # Use image or numerical analysis based on setting
                if self.send_images:
                    self._send_screenshot_for_analysis()
                else:
                    self._analyze_fit_numerically()
                return

            # Check for manual background range command (e.g., "bkg 280 295" or "background 280 295")
            bkg_match = re.search(r'(?:bkg|background)\s+(\d+\.?\d*)\s+(\d+\.?\d*)', user_lower)
            if bkg_match:
                try:
                    bg_low = float(bkg_match.group(1))
                    bg_high = float(bkg_match.group(2))
                    if bg_low > bg_high:
                        bg_low, bg_high = bg_high, bg_low
                    self._append_chat("user", question)
                    self._set_background_range(bg_low, bg_high)

                    # Lock these values so AI remembers them
                    self.locked_bg_low = bg_low
                    self.locked_bg_high = bg_high

                    self._append_chat("system", f"✅ Background range set to {bg_low:.2f} - {bg_high:.2f} eV")
                    self._append_chat("system", "💡 Type 'yes' to refit with new background, or 'done' to finish.")
                except ValueError:
                    self._append_chat("assistant", "⚠️ Invalid background values. Use format: 'bkg 280 295'")
                return

            # Check for auto background command
            if user_lower in ['auto bkg', 'auto background', 'autobkg', 'auto bg']:
                self._append_chat("user", question)
                new_bg_high = self._calculate_auto_background_high()
                if new_bg_high:
                    # Get current low BE (don't change it)
                    sheet = self.data_combo.GetValue()
                    core_data = self.window.Data['Core levels'].get(sheet, {})
                    current_bg_low = core_data.get('Background', {}).get('Bkg Low', 0)

                    self._set_background_range(current_bg_low, new_bg_high)

                    # Lock this value so AI remembers it
                    self.locked_bg_high = new_bg_high

                    self._append_chat("system", f"✅ Auto background high BE: {new_bg_high:.2f} eV (low BE unchanged: {current_bg_low:.2f} eV)")
                    self._append_chat("system", "💡 Type 'yes' to refit with new background, or 'done' to finish.")
                else:
                    self._append_chat("assistant", "⚠️ Could not calculate auto background range.")
                return

            # Check for refit command (no AI, just refit existing peaks)
            if user_lower in ['refit', 'fit again', 'fit', 'redo fit', 'redo']:
                self._append_chat("user", question)
                if self._has_existing_peaks():
                    self._refit_existing_peaks()
                else:
                    self._append_chat("assistant", "⚠️ No existing peaks to refit. Use 'Fit my data' to start fitting.")
                return

            # Check for apply command
            affirmative = ['yes', 'y', 'ok', 'okay', 'apply', 'do it', 'go ahead', 'proceed', 'sure', 'yep', 'yeah', 'apply it', 'fit it']
            if any(user_lower == a or user_lower.startswith(a + ' ') for a in affirmative):
                self._append_chat("user", question)

                # Check if we have new peaks to apply
                if self.suggested_peaks:
                    self._handle_auto_fit_apply()
                # Or if we just changed background and need to refit existing peaks
                elif self._has_existing_peaks():
                    self._refit_existing_peaks()
                else:
                    self._append_chat("assistant", "⚠️ No peak table available to apply. Please wait for a suggestion or ask for one.")
                return

            # Check for screenshot command
            if 'screenshot' in user_lower or 'send screenshot' in user_lower or 'inspect' in user_lower:
                self._append_chat("user", question)
                self._send_screenshot_for_analysis()
                return

            # Check for residual analysis command
            if 'residual' in user_lower or 'analyse' in user_lower or 'analyze' in user_lower:
                self._append_chat("user", question)
                self._analyze_residuals_after_fit()
                return

            # Check for done/finish command
            done_commands = ['done', 'finish', 'finished', 'complete', 'exit', 'quit', 'stop']
            if any(user_lower == d or user_lower.startswith(d + ' ') for d in done_commands):
                self._append_chat("user", question)
                current_rsd = self._get_current_rsd()
                self._append_chat("assistant", f"👋 Fit session ended. Final RSD: {current_rsd:.2f}%")
                self.auto_fit_mode = False
                self.auto_fit_stage = None
                # Clear locked background values
                self.locked_bg_low = None
                self.locked_bg_high = None
                return

            # Check for cancel command (without applying)
            cancel_commands = ['cancel', 'abort', 'nevermind', 'nope', 'no']
            if any(user_lower == c for c in cancel_commands):
                self._append_chat("user", question)
                self._append_chat("assistant", "👋 Fit session cancelled. No changes applied.")
                self.auto_fit_mode = False
                self.auto_fit_stage = None
                self.suggested_peaks = []
                self.suggested_bg_range = None
                self.apply_btn.Enable(False)
                return

            # Any other input is treated as a modification/continuation request
            element = self._get_element_from_core_level(self.data_combo.GetValue())

            # Add instruction to always provide updated table
            enhanced_question = f"""{question}

        IMPORTANT: Provide an updated peak fitting table using this format:

        Background Range: XXX.XX - YYY.YY eV

        | ID | Label           | Position      | FWHM       | L/G   | Area   | Model      |
        |----|-----------------|---------------|------------|-------|--------|------------|
        | A  | ...             | XXX.XX        | X.XX       | XX    | ---    | SGL (Area) |
        |    |                 | constraint    | ...        | ...   | ...    |            |

        When showing peak tables, use fixed-width monospace formatting with aligned columns.

        Then ask: "Would you like me to apply this fitting? Reply 'yes' to apply, or describe further changes."
        """

            # Display only the user's original question, not the enhanced version
            self._send_query(enhanced_question, element, parse_peaks=True, display_label=question)
            return

        # Normal (non-auto-fit) flow
        element = None
        sheet = self.data_combo.GetValue()
        if sheet:
            element = self._get_element_from_core_level(sheet)

        match = re.search(r'\b([A-Z][a-z]?)\s*\d[spdf]', question)
        if match:
            element = match.group(1)

        # Detect user intent from natural language
        intent = self._detect_intent(question)

        if intent == 'identify':
            # Trigger Identify Peaks button action
            self._append_chat("user", question)
            self.on_identify(None)
            return
        elif intent == 'suggest' or intent == 'fit':
            # Trigger Suggest Fitting button action
            self._append_chat("user", question)
            self.on_suggest_fitting(None)
            return
        elif intent == 'auto_fit':
            # Trigger Auto Fit button action
            self._append_chat("user", question)
            self.on_auto_fit(None)
            return

        # Default: send as general question
        self._send_query(question, element)

    def _set_background_range(self, bg_low, bg_high):
        """Set background range without changing peak table"""
        try:
            sheet = self.data_combo.GetValue()
            if not sheet:
                return False

            core_data = self.window.Data['Core levels'].get(sheet, {})
            x_values = np.array(core_data.get('B.E.', core_data.get('BE', [])))
            y_values = np.array(core_data.get('Raw Data', []))

            # Clamp to spectrum range
            bg_low = max(bg_low, float(np.min(x_values)))
            bg_high = min(bg_high, float(np.max(x_values)))

            # Update background in data structure
            if 'Background' not in core_data:
                core_data['Background'] = {}

            core_data['Background']['Bkg Low'] = float(f"{bg_low:.2f}")
            core_data['Background']['Bkg High'] = float(f"{bg_high:.2f}")

            # Update window variables
            self.window.bg_min_energy = float(f"{bg_low:.2f}")
            self.window.bg_max_energy = float(f"{bg_high:.2f}")

            # Update vlines if they exist
            if hasattr(self.window, 'vline1') and self.window.vline1 is not None:
                self.window.vline1.set_xdata([bg_high, bg_high])
            if hasattr(self.window, 'vline2') and self.window.vline2 is not None:
                self.window.vline2.set_xdata([bg_low, bg_low])

            # Update fitting window if open
            if hasattr(self.window, 'fitting_window') and self.window.fitting_window:
                try:
                    self.window.fitting_window.updating_range_controls = True
                    self.window.fitting_window.min_range_text.SetValue(f"{bg_low:.2f}")
                    self.window.fitting_window.max_range_text.SetValue(f"{bg_high:.2f}")
                    self.window.fitting_window.updating_range_controls = False
                except:
                    pass

            # Recalculate background
            self._recalculate_background(sheet, bg_low, bg_high)

            # Replot
            if hasattr(self.window, 'clear_and_replot'):
                self.window.clear_and_replot()

            return True

        except Exception as e:
            print(f"DEBUG: Error setting background range: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _recalculate_background(self, sheet, bg_low, bg_high):
        """Recalculate background with new range"""
        try:
            from libraries.Peak_Functions import BackgroundCalculations

            core_data = self.window.Data['Core levels'].get(sheet, {})
            x_values = np.array(core_data.get('B.E.', core_data.get('BE', [])))
            y_values = np.array(core_data.get('Raw Data', []))

            mask = (x_values >= bg_low) & (x_values <= bg_high)
            x_filtered = x_values[mask]
            y_filtered = y_values[mask]

            bg_method = core_data.get('Background', {}).get('Method', 'Active Shirley')

            if bg_method == "Active Shirley":
                offset_h = float(core_data.get('Background', {}).get('Bkg Offset High', 0))
                offset_l = float(core_data.get('Background', {}).get('Bkg Offset Low', 0))
                new_bg_filtered = BackgroundCalculations.calculate_active_shirley_background(
                    x_filtered, y_filtered, offset_h=offset_h, offset_l=offset_l, num_points=5
                )
            else:
                new_bg_filtered = BackgroundCalculations.calculate_shirley_background(x_filtered, y_filtered)

            # Update full background array
            full_background = y_values.copy()
            full_background[mask] = new_bg_filtered

            core_data['Background']['Bkg Y'] = full_background.tolist()
            self.window.background = np.array(full_background)

        except Exception as e:
            print(f"DEBUG: Error recalculating background: {e}")

    def _calculate_auto_background_high(self):
        """Calculate optimal high BE background by finding where (Raw - Bkg) goes most negative"""
        try:
            sheet = self.data_combo.GetValue()
            if not sheet:
                return None

            core_data = self.window.Data['Core levels'].get(sheet, {})
            x_values = np.array(core_data.get('B.E.', core_data.get('BE', [])))
            y_values = np.array(core_data.get('Raw Data', []))
            background = np.array(core_data.get('Background', {}).get('Bkg Y', []))

            if len(x_values) == 0 or len(background) == 0:
                return None

            # Get current peaks to find highest BE peak
            peaks = core_data.get('Fitting', {}).get('Peaks', {})
            if not peaks:
                # Fallback to current calculation
                return self._calculate_background_range_from_peaks().get('high')

            # Find highest BE peak position and its FWHM
            max_be_pos = 0
            max_be_fwhm = 1.0

            for label, peak_data in peaks.items():
                pos = peak_data.get('Position', 0)
                fwhm = peak_data.get('FWHM', 1.0)
                if pos > max_be_pos:
                    max_be_pos = pos
                    max_be_fwhm = fwhm

            # Calculate subtracted data (Raw - Background)
            subtracted = y_values - background

            # Search region: start after highest peak + FWHM
            search_start = max_be_pos + max_be_fwhm
            high_be_mask = x_values > search_start

            if np.any(high_be_mask):
                subtracted_high_be = subtracted[high_be_mask]
                x_high_be = x_values[high_be_mask]

                # Find the position where subtracted data is most negative (lowest value)
                if len(subtracted_high_be) > 0:
                    min_idx = np.argmin(subtracted_high_be)
                    bg_high = float(x_high_be[min_idx])
                else:
                    bg_high = max_be_pos + max_be_fwhm + 0.5
            else:
                bg_high = max_be_pos + max_be_fwhm + 0.5

            # Clamp to spectrum range
            bg_high = min(bg_high, float(np.max(x_values)))

            return float(f"{bg_high:.2f}")

        except Exception as e:
            print(f"DEBUG: Error calculating auto background high: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _has_existing_peaks(self):
        """Check if current sheet has existing fitted peaks"""
        try:
            sheet = self.data_combo.GetValue()
            if not sheet:
                return False
            core_data = self.window.Data['Core levels'].get(sheet, {})
            peaks = core_data.get('Fitting', {}).get('Peaks', {})
            return len(peaks) > 0
        except:
            return False

    def _refit_existing_peaks(self):
        """Refit with existing peaks (after background change)"""
        self._append_chat("system", "🔄 Refitting with updated background...")

        try:
            # Trigger fitting with 20 iterations
            fit_iterations = 20
            if hasattr(self.window, 'fitting_window') and self.window.fitting_window:
                try:
                    if hasattr(self.window.fitting_window, 'fit_iterations_spin'):
                        self.window.fitting_window.fit_iterations_spin.SetValue(fit_iterations)
                    self.window.fitting_window.on_fit_multi(None)
                except Exception as e:
                    print(f"DEBUG: Error triggering fit: {e}")
                    self._perform_initial_fit()
            else:
                self._perform_initial_fit()

            # Replot
            if hasattr(self.window, 'clear_and_replot'):
                self.window.clear_and_replot()

            self._append_chat("system", f"🔄 Fitted {fit_iterations} iterations")

            # Get new RSD and show result
            current_rsd = self._get_current_rsd()
            self._append_chat("system", f"📊 Refit complete. RSD: {current_rsd:.2f}")

            if current_rsd < 1.0:
                self._append_chat("system", f"✅ Excellent fit! RSD: {current_rsd:.2f} (target: <1)")

            self._append_chat("system", "💡 Type 'send screenshot' to inspect, 'continue', 'refit', 'bkg XXX YYY', 'auto bkg', or 'done' to finish.")

        except Exception as e:
            import traceback
            traceback.print_exc()
            self._append_chat("assistant", f"❌ Error refitting: {str(e)}")

    def _detect_intent(self, question):
        """Detect user intent from natural language input"""
        q = question.lower().strip()

        # Identify peaks intent
        identify_patterns = [
            'identify', 'what species', 'what peaks', 'what chemical',
            'which species', 'which peaks', 'which chemical',
            'what is in my', 'what are the peaks', 'what compounds',
            'analyze my spectrum', 'analyse my spectrum',
            'what do i have', 'what\'s in my', 'whats in my',
            'help me identify', 'can you identify',
            'what elements', 'what states', 'chemical states'
        ]
        for pattern in identify_patterns:
            if pattern in q:
                return 'identify'

        # Auto fit intent (more specific, check first)
        auto_fit_patterns = [
            'auto fit', 'autofit', 'auto-fit',
            'fit automatically', 'automatic fit',
            'fit it for me', 'fit this for me',
            'do the fitting', 'perform fitting',
            'fit my data', 'fit my spectrum',
            'fit the data', 'fit the spectrum',
            'fit this data', 'fit this spectrum'
        ]
        for pattern in auto_fit_patterns:
            if pattern in q:
                return 'auto_fit'

        # Suggest fitting intent
        suggest_patterns = [
            'suggest fit', 'suggest a fit', 'suggest fitting',
            'how should i fit', 'how to fit', 'how do i fit',
            'fit my', 'fitting for', 'peak model',
            'propose fit', 'propose a fit', 'propose fitting',
            'recommend fit', 'recommend fitting',
            'give me a fit', 'create a fit', 'create fit',
            'make a fit', 'build a fit', 'set up fit',
            'fitting model', 'peak fitting'
        ]
        for pattern in suggest_patterns:
            if pattern in q:
                return 'suggest'

        # No specific intent detected - general question
        return None

    def _initialize_conversation_with_knowledge_OLD(self):
        """Load knowledge base once at conversation initialization"""
        if not hasattr(self, '_kb_loaded') or not self._kb_loaded:
            kb_content = self._load_knowledge_base_for_chat()
            if kb_content and len(kb_content) > 100:
                self.conversation_history.append({
                    "role": "user",
                    "content": "Here is my knowledge base for reference:\n" + kb_content
                })
                self.conversation_history.append({
                    "role": "assistant",
                    "content": "I've loaded the KherveFitting knowledge base. I'm ready to help with XPS analysis."
                })
                self._kb_loaded = True

    def _load_knowledge_base_for_chat(self, max_total_chars=80000):
        """Load knowledge base files with size limit to prevent context overflow"""

        knowledge_files = [
            'KherveFitting_Knowledge.md',
            'XPS_Knowledge.md',
            'Multiplet_and_CosterKronig.md'
        ]

        kb_content = "Reference knowledge base:\n\n"
        chars_per_file = max_total_chars // len(knowledge_files)

        for filename in knowledge_files:
            file_path = os.path.join(self.DOCS_PATH, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if len(content) > chars_per_file:
                        content = content[:chars_per_file] + "\n[...truncated...]"
                    kb_content += f"\n{'=' * 40}\n{filename}\n{'=' * 40}\n{content}\n"
            except FileNotFoundError:
                print(f"Knowledge base not found: {file_path}")
            except Exception as e:
                print(f"Error loading {filename}: {e}")

        if len(kb_content) > max_total_chars:
            kb_content = kb_content[:max_total_chars] + "\n\n[Knowledge base truncated]"

        return kb_content

    def _send_query_OLD(self, question, element=None, parse_peaks=False, display_label=None):
        """Send query to API with streaming"""
        # Show short label in chat if provided, otherwise show full question
        chat_display_text = display_label if display_label else question
        self._append_chat("user", chat_display_text)
        self._update_status("KherveAI is thinking...", "blue")
        self._enable_buttons(False)
        self.parse_peaks_flag = parse_peaks

        def run():
            try:
                self._query_api_streaming(question, element)
            except Exception as e:
                wx.CallAfter(self._show_error, str(e))

        t = threading.Thread(target=run, daemon=True)
        t.start()

    def _send_query(self, question, element=None, parse_peaks=False, display_label=None):
        """Send query to API with streaming"""
        # Show short label in chat if provided, otherwise show full question
        chat_display_text = display_label if display_label else question
        self._append_chat("user", chat_display_text)

        # Add to conversation history
        spectrum_data = None
        if hasattr(self, 'current_spectrum_data'):
            spectrum_data = self.current_spectrum_data

        # self._add_to_history('user', question, element=element, spectrum_data=spectrum_data)

        self._update_status("KherveAI is thinking...", "blue")
        self._enable_buttons(False)
        self.parse_peaks_flag = parse_peaks

        def run():
            try:
                self._query_api_streaming(question, element)
            except Exception as e:
                wx.CallAfter(self._show_error, str(e))

        t = threading.Thread(target=run, daemon=True)
        t.start()

    def _convert_latex_to_text(self, latex_text):
        """Convert LaTeX math syntax to readable text"""
        text = latex_text

        # Handle \text{...}
        text = re.sub(r'\\text\{([^}]+)\}', r'\1', text)

        # Handle \frac{num}{den} -> (num/den)
        text = re.sub(r'\\frac\{([^}]+)\}\{([^}]+)\}', r'(\1/\2)', text)

        # Handle \sum -> Σ
        text = text.replace(r'\sum', 'Σ')

        # Handle subscripts _{...} -> convert to plain subscript numbers/letters
        def replace_subscript(match):
            sub_text = match.group(1)
            # Common subscript mappings
            sub_map = {
                '0': '₀', '1': '₁', '2': '₂', '3': '₃', '4': '₄',
                '5': '₅', '6': '₆', '7': '₇', '8': '₈', '9': '₉',
                'x': 'ₓ', 'i': 'ᵢ', 'n': 'ₙ', 'a': 'ₐ', 'e': 'ₑ',
                'o': 'ₒ', 'r': 'ᵣ', 'u': 'ᵤ', 'v': 'ᵥ'
            }
            result = ''
            for char in sub_text:
                result += sub_map.get(char, char)
            return result

        text = re.sub(r'_\{([^}]+)\}', replace_subscript, text)
        text = re.sub(r'_([a-zA-Z0-9])', lambda m: replace_subscript(type('obj', (object,), {'group': lambda self, n: m.group(1)})()).replace('_{', '').replace('}', ''), text)

        # Handle superscripts ^{...}
        def replace_superscript(match):
            sup_text = match.group(1)
            sup_map = {
                '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
                '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹',
                '+': '⁺', '-': '⁻', '=': '⁼', '(': '⁽', ')': '⁾',
                'n': 'ⁿ', 'i': 'ⁱ'
            }
            result = ''
            for char in sup_text:
                result += sup_map.get(char, char)
            return result

        text = re.sub(r'\^\{([^}]+)\}', replace_superscript, text)
        text = re.sub(r'\^([a-zA-Z0-9])', lambda m: replace_superscript(type('obj', (object,), {'group': lambda self, n: m.group(1)})()), text)

        # Handle Greek letters
        greek_map = {
            r'\nu': 'ν', r'\Phi': 'Φ', r'\phi': 'φ', r'\alpha': 'α',
            r'\beta': 'β', r'\gamma': 'γ', r'\delta': 'δ', r'\epsilon': 'ε',
            r'\theta': 'θ', r'\lambda': 'λ', r'\mu': 'μ', r'\pi': 'π',
            r'\sigma': 'σ', r'\tau': 'τ', r'\omega': 'ω', r'\Delta': 'Δ',
            r'\Gamma': 'Γ', r'\Lambda': 'Λ', r'\Sigma': 'Σ', r'\Omega': 'Ω'
        }
        for latex, unicode_char in greek_map.items():
            text = text.replace(latex, unicode_char)

        return text

    def _query_api_streaming(self, question, element=None):
        """Query ChatGPT API with streaming for live response"""
        if not self.api_key:
            wx.CallAfter(self._show_error, "No API key. Go to Edit > Configuration.")
            return

        messages = [{"role": "system", "content": self._build_system_prompt()}]

        # Send element context once
        if element:
            context = self._build_element_context(element)
            if context:
                messages.append({"role": "user", "content": f"[Reference]\n{context}"})
                messages.append({"role": "assistant", "content": f"Loaded {element} reference data."})

        # Add conversation history (last 10 messages to reduce context size)
        for msg in self.conversation_history[-10:]:
            messages.append(msg)

        messages.append({"role": "user", "content": question})

        # ===== DEBUG: Print full OpenAI request =====
        total_chars = sum(len(m.get('content', '')) for m in messages)
        print("\n" + "="*80)
        print("DEBUG: FULL OPENAI REQUEST")
        print("="*80)
        print(f"Model: {self.model}")
        print(f"Total messages: {len(messages)}")
        print(f"Total characters: {total_chars}")
        print("-"*80)
        for i, msg in enumerate(messages):
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            print(f"\n[Message {i+1}] Role: {role.upper()}")
            print(f"Content length: {len(content)} chars")
            print("-"*40)
            if len(content) > 8000:
                print(content[:4000])
                print(f"\n... [TRUNCATED {len(content)-8000} chars] ...\n")
                print(content[-4000:])
            else:
                print(content)
            print("-"*40)
        print("="*80 + "\n")
        # ===== END DEBUG =====

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # O1 and GPT-5 models use different parameters
        is_o1_or_gpt5 = any(x in self.model for x in ['o1', 'o3', 'gpt-5'])

        data = {
            "model": self.model,
            "messages": messages,
            "stream": True
        }

        # O1/GPT-5 models use max_completion_tokens, others use max_tokens
        if is_o1_or_gpt5:
            data["max_completion_tokens"] = self.max_tokens
        else:
            data["temperature"] = self.temperature
            data["max_tokens"] = self.max_tokens

        wx.CallAfter(self._start_assistant_bubble)

        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers, json=data, timeout=120, stream=True
            )

            if response.status_code == 401:
                wx.CallAfter(self._show_error, "Invalid API key.")
                return
            if response.status_code == 429:
                wx.CallAfter(self._show_error, "Rate limit. Wait and try again.")
                return
            if response.status_code == 400:
                error_text = response.text[:500]
                wx.CallAfter(self._show_error, f"Model '{self.model}' is not supported for chat.\n\nPlease select a different model from the Model menu.\n\nError: {error_text}")
                return
            if response.status_code != 200:
                error_text = response.text[:500]
                wx.CallAfter(self._show_error, f"API error: {response.status_code}\n{error_text}")
                return

            full_response = ""
            for line in response.iter_lines():
                if line:
                    line_text = line.decode('utf-8')
                    if line_text.startswith('data: '):
                        json_str = line_text[6:]
                        if json_str.strip() == '[DONE]':
                            # print("DEBUG: Stream completed [DONE]")
                            break
                        try:
                            chunk = json.loads(json_str)
                            if 'choices' in chunk and len(chunk['choices']) > 0:
                                delta = chunk['choices'][0].get('delta', {})
                                content = delta.get('content', '')
                                if content:
                                    full_response += content
                                    wx.CallAfter(self._stream_text, content)

                                # Check for finish reason
                                finish_reason = chunk['choices'][0].get('finish_reason')
                        except json.JSONDecodeError as e:
                            print(f"DEBUG: JSON decode error: {e}")

            # print(f"DEBUG: Full response length: {len(full_response)}")

            # Save to history
            self.conversation_history.append({"role": "user", "content": question})
            self.conversation_history.append({"role": "assistant", "content": full_response})

            wx.CallAfter(self._finish_streaming, full_response)

        except Exception as e:
            print(f"DEBUG: Exception: {e}")
            wx.CallAfter(self._show_error, str(e))

    def _detect_repetition(self, text, min_pattern_len=10, max_repeats=3):
        """Detect if text contains repetitive patterns"""
        if len(text) < min_pattern_len * max_repeats:
            return False

        # Check last portion for repetition
        check_len = min(500, len(text))
        recent = text[-check_len:]

        # Look for repeating patterns
        for pattern_len in range(min_pattern_len, check_len // max_repeats):
            pattern = recent[-pattern_len:]
            count = recent.count(pattern)
            if count >= max_repeats:
                return True
        return False

    def _start_assistant_bubble(self):
        """Start the assistant response bubble"""
        timestamp = datetime.datetime.now().strftime("%H:%M")

        self.chat_display.SetInsertionPointEnd()
        self.chat_display.Newline()

        # Header - orange/gold
        header_style = wx.richtext.RichTextAttr()
        header_style.SetTextColour(wx.Colour(70, 70, 95))
        header_style.SetFontSize(12)
        header_style.SetFontWeight(wx.FONTWEIGHT_BOLD)
        header_style.SetAlignment(wx.TEXT_ALIGNMENT_LEFT)

        self.chat_display.BeginStyle(header_style)

        # Try to load and insert icon
        icon_path = os.path.join(os.path.dirname(__file__), 'khervefitting_icon.png')
        if os.path.exists(icon_path):
            try:
                img = wx.Image(icon_path, wx.BITMAP_TYPE_PNG)
                img.Rescale(18, 18, wx.IMAGE_QUALITY_HIGH)
                bitmap = wx.Bitmap(img)
                if bitmap.IsOk():
                    self.chat_display.WriteImage(bitmap)
                    self.chat_display.WriteText(f" KherveAI  {timestamp}")
            except:
                self.chat_display.WriteText(f"KherveAI  {timestamp}")
        else:
            self.chat_display.WriteText(f"KherveAI  {timestamp}")

        self.chat_display.EndStyle()
        self.chat_display.Newline()

        # Save position where content starts (for reformatting later)
        self.stream_start_pos = self.chat_display.GetLastPosition()

        # Start message style - yellow for streaming
        self.streaming_style = wx.richtext.RichTextAttr()
        self.streaming_style.SetFontWeight(wx.FONTWEIGHT_NORMAL)
        self.streaming_style.SetTextColour(wx.Colour(0, 0, 0))  # Yellow
        self.streaming_style.SetFontSize(11)

        self.chat_display.BeginStyle(self.streaming_style)

    def _write_equation(self, equation_text):
        """Write mathematical equations with special formatting"""
        # Convert LaTeX to readable text
        converted_text = self._convert_latex_to_text(equation_text)

        eq_style = wx.richtext.RichTextAttr()
        eq_style.SetTextColour(wx.Colour(0, 100, 150))
        eq_style.SetFontFamily(wx.FONTFAMILY_TELETYPE)
        eq_style.SetFontSize(10)

        self.chat_display.WriteText("      ")
        self.chat_display.BeginStyle(eq_style)
        self.chat_display.WriteText(converted_text)
        self.chat_display.EndStyle()
        self.chat_display.Newline()

    def _stream_text(self, text):
        """Stream text to the current response with basic formatting"""
        self.chat_display.WriteText(text)
        self.chat_display.ShowPosition(self.chat_display.GetLastPosition())


    def _format_and_append_text(self, text):
        # print(f'Get the whole text\n {text} \n End of text')
        """Format text with markdown-like styling and append to chat"""

        # # Set justified alignment for all text
        # attr = wx.richtext.RichTextAttr()
        # attr.SetAlignment(wx.TEXT_ALIGNMENT_JUSTIFIED)
        # self.chat_display.BeginStyle(attr)

        # Split numbered items that are on the same line (e.g., "1. xxx  2. yyy")
        text = re.sub(r'(\d+\.)\s{2,}(\d+\.)', r'\1\n\2', text)
        # Also split on pattern like "text.  1."
        text = re.sub(r'\.(\s{2,})(\d+\.)', r'.\n\2', text)

        lines = text.split('\n')
        in_equation = False
        equation_lines = []
        prev_was_header = False

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Handle equation blocks - detect \[ on its own line
            if stripped == r'\[':
                in_equation = True
                equation_lines = []
                continue
            elif stripped == r'\]':
                if in_equation:
                    # Write the complete equation
                    equation_text = ' '.join(equation_lines)
                    self._write_equation(equation_text)
                    in_equation = False
                    equation_lines = []
                continue
            elif in_equation:
                equation_lines.append(stripped)
                continue

            if not stripped:
                if not prev_was_header:
                    self.chat_display.Newline()
                prev_was_header = False
                continue

            if stripped.startswith('###'):
                # H3 Header - bold yellow
                header_style = wx.richtext.RichTextAttr()
                header_style.SetTextColour(wx.Colour(105, 105, 128))
                header_style.SetFontWeight(wx.FONTWEIGHT_BOLD)
                header_style.SetFontSize(11)
                self.chat_display.BeginStyle(header_style)
                self.chat_display.WriteText(stripped.replace('###', '').strip())
                self.chat_display.EndStyle()
                self.chat_display.Newline()
                prev_was_header = True

            elif stripped.startswith('##'):
                # H2 Header - bold orange
                header_style = wx.richtext.RichTextAttr()
                header_style.SetTextColour(wx.Colour(105, 105, 128))
                header_style.SetFontWeight(wx.FONTWEIGHT_BOLD)
                header_style.SetFontSize(12)
                self.chat_display.BeginStyle(header_style)
                self.chat_display.WriteText(stripped.replace('##', '').strip())
                self.chat_display.EndStyle()
                self.chat_display.Newline()
                prev_was_header = True

            elif stripped.startswith('#'):
                # H1 Header - bold gold
                header_style = wx.richtext.RichTextAttr()
                header_style.SetTextColour(wx.Colour(105, 105, 128))
                header_style.SetFontWeight(wx.FONTWEIGHT_BOLD)
                header_style.SetFontSize(13)
                self.chat_display.BeginStyle(header_style)
                self.chat_display.WriteText(stripped.replace('#', '').strip())
                self.chat_display.EndStyle()
                self.chat_display.Newline()
                prev_was_header = True

            elif stripped and re.match(r'^\d+\.\s', stripped):
                # Numbered list - with inline formatting support
                self.chat_display.WriteText("  ")
                self._write_with_inline_formatting(stripped)
                self.chat_display.Newline()
                prev_was_header = False

            elif stripped.startswith('  - ') or stripped.startswith('  * '):
                # Nested bullet point (indented)
                bullet_style = wx.richtext.RichTextAttr()
                bullet_style.SetTextColour(wx.Colour(0, 0, 0))
                bullet_style.SetFontSize(11)
                self.chat_display.BeginStyle(bullet_style)
                self.chat_display.WriteText("    • ")
                self.chat_display.EndStyle()
                self._write_with_inline_formatting(stripped[4:].strip())
                self.chat_display.Newline()
                prev_was_header = False

            elif stripped.startswith('- ') or stripped.startswith('* '):
                # Bullet point - with bullet character
                bullet_style = wx.richtext.RichTextAttr()
                bullet_style.SetTextColour(wx.Colour(0, 0, 0))
                bullet_style.SetFontSize(11)
                self.chat_display.BeginStyle(bullet_style)
                self.chat_display.WriteText("  • ")
                self.chat_display.EndStyle()
                # Use inline formatting for the bullet text (handles **bold** etc)
                self._write_with_inline_formatting(stripped[2:])
                self.chat_display.Newline()
                prev_was_header = False
            else:
                # Regular text or inline bold - process inline formatting
                self._write_with_inline_formatting(stripped)
                self.chat_display.Newline()
                prev_was_header = False


    def _write_with_inline_formatting(self, text):
        """Write text with inline formatting like **bold** and inline equations"""
        # Pattern matches: \( ... \) or **...**
        pattern = r'(\\\\?\([^)]*\\\\?\)|\*\*[^*]+\*\*)'
        parts = re.split(pattern, text)

        for part in parts:
            if not part:
                continue

            # Check for inline equation
            if (part.startswith(r'\(') or part.startswith('\\(')) and (part.endswith(r'\)') or part.endswith('\\)')):
                # Inline equation - strip delimiters and convert LaTeX
                eq_text = part.replace(r'\(', '').replace(r'\)', '').replace('\\(', '').replace('\\)', '').strip()
                eq_text = self._convert_latex_to_text(eq_text)

                eq_style = wx.richtext.RichTextAttr()
                eq_style.SetTextColour(wx.Colour(0, 100, 150))
                eq_style.SetFontFamily(wx.FONTFAMILY_TELETYPE)
                eq_style.SetFontSize(10)
                self.chat_display.BeginStyle(eq_style)
                self.chat_display.WriteText(eq_text)
                self.chat_display.EndStyle()
            elif part.startswith('**') and part.endswith('**'):
                # Bold text
                bold_style = wx.richtext.RichTextAttr()
                bold_style.SetFontWeight(wx.FONTWEIGHT_BOLD)
                bold_style.SetTextColour(wx.Colour(0, 0, 0))
                self.chat_display.BeginStyle(bold_style)
                self.chat_display.WriteText(part[2:-2])
                self.chat_display.EndStyle()
            else:
                # Regular text
                normal_style = wx.richtext.RichTextAttr()
                normal_style.SetTextColour(wx.Colour(0, 0, 0))
                normal_style.SetAlignment(wx.TEXT_ALIGNMENT_JUSTIFIED)
                normal_style.SetFontSize(11)
                self.chat_display.BeginStyle(normal_style)
                self.chat_display.WriteText(part)
                self.chat_display.EndStyle()

    def _finish_streaming(self, full_response):
        """Finish streaming and reformat the complete response"""
        # Add assistant response to history
        self._add_to_history('assistant', full_response)

        # Clear the streamed text and replace with formatted version
        # Find where the assistant response started and delete it

        # End current style
        self.chat_display.EndStyle()

        # Delete the raw streamed content (from stream_start_pos to end)
        if hasattr(self, 'stream_start_pos'):
            self.chat_display.Remove(self.stream_start_pos, self.chat_display.GetLastPosition())
            self.chat_display.SetInsertionPoint(self.stream_start_pos)

        # Now write formatted response
        self._format_and_append_text(full_response)
        self.chat_display.Newline()
        self.chat_display.ShowPosition(self.chat_display.GetLastPosition())

        self._update_status("Ready", "green")
        self._enable_buttons(True)

        if getattr(self, 'parse_peaks_flag', False):
            self._parse_suggested_peaks(full_response)

    def _show_error(self, error_msg):
        """Show error message"""
        self._append_chat("assistant", f"Error: {error_msg}")
        self._update_status("Error", "red")
        self._enable_buttons(True)

    def _build_system_prompt(self):
        """Build technique-specific system prompt with verbosity control"""
        technique = getattr(self, 'current_technique', 'XPS')
        verbosity = getattr(self, 'response_verbosity', 'Concise')

        # Get verbosity instruction from prompts file
        verbosity_key = f"VERBOSITY_{verbosity.upper()}"
        verbosity_instruction = self._get_prompt(verbosity_key)
        if not verbosity_instruction:
            # Fallback
            if verbosity == "Concise":
                verbosity_instruction = "RESPONSE STYLE: Be VERY CONCISE. Use bullet points, tables only, minimal text."
            elif verbosity == "Extended":
                verbosity_instruction = "RESPONSE STYLE: Be DETAILED and EDUCATIONAL."
            else:
                verbosity_instruction = "RESPONSE STYLE: Be BALANCED."

        # Get technique-specific prompt from prompts file
        technique_key = f"SYSTEM_PROMPT_{technique.upper()}"
        base_prompt = self._get_prompt(technique_key)

        if not base_prompt:
            base_prompt = self._get_prompt("SYSTEM_PROMPT_DEFAULT")

        if not base_prompt:
            # Fallback if prompts file not loaded
            base_prompt = f"""You are KherveAI, an expert {technique} analyst assistant for KherveFitting software.

Your expertise:
1. Identify chemical states from binding energies
2. Suggest peak fitting parameters (position, FWHM, constraints)
3. Explain spin-orbit splitting, shake-up satellites
4. Recommend background subtraction methods

Rules:
- Format binding energies as XXX.XX eV
- Format FWHM as X.XX eV
- Use the reference documentation provided for each element"""

        return f"{base_prompt}\n\n{verbosity_instruction}"

    def _build_system_prompt_OLD(self):
        """Build technique-specific system prompt with verbosity control"""
        technique = getattr(self, 'current_technique', 'XPS')
        verbosity = getattr(self, 'response_verbosity', 'Normal')

        # Verbosity instructions
        if verbosity == "Concise":
            verbosity_instruction = """
RESPONSE STYLE: Be VERY CONCISE. 
- Use bullet points only
- No explanations unless critical
- Skip greetings and pleasantries
- Maximum 5-6 lines for analysis
- Go straight to recommendations
- Tables only, minimal text"""
        elif verbosity == "Extended":
            verbosity_instruction = """
RESPONSE STYLE: Be DETAILED and EDUCATIONAL.
- Explain the reasoning behind recommendations
- Include relevant XPS theory when helpful
- Discuss alternative interpretations
- Provide context for binding energy assignments
- Explain why certain constraints are recommended
- Include references to literature values when available"""
        else:  # Normal
            verbosity_instruction = """
RESPONSE STYLE: Be BALANCED.
- Clear and informative but not verbose
- Include key reasoning without excessive detail
- Provide recommendations with brief justification
- Use tables for peak parameters"""

        if technique == "XPS":
            return f"""You are KherveAI, an expert XPS (X-ray Photoelectron Spectroscopy) analyst assistant for KherveFitting software.

Your expertise:
1. Identify chemical states from binding energies
2. Suggest peak fitting parameters (position, FWHM, constraints)
3. Explain spin-orbit splitting, shake-up satellites, Auger parameters
4. Recommend background subtraction methods (Shirley, Tougaard)

{verbosity_instruction}

Rules:
- Only respond to questions related to the technique or Materials Science or KherveFitting or Reference to journals/papers
- Use the reference documentation provided for each element
- Format binding energies as XXX.XX eV
- Format FWHM as X.XX eV  
- When suggesting peaks: Peak N: XXX.XX eV, FWHM: X.XX eV - Assignment
- For identifying peaks chemical or oxidation states, do not use the FWHM but binding energy position of the peaks.
- Always mention doublet constraints for p, d, f orbitals
- List the References provided in the documentation
- If requested provide a peak fitting table  
- In tables, use this format: | Element | Pos. (eV) | FWHM (eV) | Assignment |"""

        elif technique == "EELS":
            return f"""You are KherveAI, an expert EELS (Electron Energy Loss Spectroscopy) analyst assistant.

Your expertise:
1. Identify core-loss edges and their fine structure
2. Explain plasmon peaks and their origins
3. Assist with background subtraction (power-law)
4. Help with quantification and edge analysis

{verbosity_instruction}

Rules:
- Reference energy loss values accurately
- Explain near-edge fine structure (ELNES) when relevant"""

        elif technique == "EDX":
            return f"""You are KherveAI, an expert EDX/EDS (Energy Dispersive X-ray) analyst assistant.

Your expertise:
1. Identify characteristic X-ray peaks (K, L, M lines)
2. Explain peak overlaps and interferences
3. Assist with quantification considerations
4. Discuss detection limits and artifacts

{verbosity_instruction}

Rules:
- Reference X-ray line energies accurately
- Mention potential peak overlaps"""

        elif technique == "Raman":
            return f"""You are KherveAI, an expert Raman spectroscopy analyst assistant.

Your expertise:
1. Identify Raman-active vibrational modes
2. Explain peak assignments for common materials
3. Discuss crystallinity and phase identification
4. Help with peak fitting

{verbosity_instruction}

Rules:
- Reference Raman shifts in cm⁻¹
- Consider fluorescence backgrounds"""

        else:
            return f"""You are KherveAI, a spectroscopy analyst assistant for {technique}.

Your role:
1. Help identify spectral features
2. Suggest peak fitting parameters
3. Explain relevant concepts

{verbosity_instruction}

Rules:
- Be accurate with energy/frequency values
- Use .2f precision for numerical values"""

    def _parse_suggested_peaks(self, result):
        """Parse peak suggestions from response - handles table format with constraints and background range"""
        self.suggested_peaks = []
        self.suggested_bg_range = None

        # Extract background range - try multiple patterns
        bg_patterns = [
            r'Background\s*Range[:\s]*(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)\s*eV',
            r'Range[:\s]*[Tt]ypically\s*(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)\s*eV',
            r'Range[:\s]*(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)\s*eV',
            r'(\d{2,3}\.?\d*)\s*[-–]\s*(\d{2,3}\.?\d*)\s*eV.*[Bb]ackground',
            r'[Bb]ackground.*(\d{2,3}\.?\d*)\s*[-–]\s*(\d{2,3}\.?\d*)\s*eV',
        ]

        for pattern in bg_patterns:
            bg_match = re.search(pattern, result, re.I)
            if bg_match:
                try:
                    low = float(bg_match.group(1))
                    high = float(bg_match.group(2))
                    if low > high:
                        low, high = high, low
                    self.suggested_bg_range = {'low': low, 'high': high}
                    print(f"DEBUG: Parsed background range: {self.suggested_bg_range['low']:.2f} - {self.suggested_bg_range['high']:.2f} eV")
                    break
                except (ValueError, IndexError):
                    continue

        if not self.suggested_bg_range:
            print("DEBUG: No background range found in AI response")

        # Try to parse the markdown table format
        lines = result.split('\n')
        current_peak = None

        for line in lines:
            line = line.strip()
            if not line or line.startswith('|--') or line.startswith('| ID'):
                continue

            if line.startswith('|'):
                parts = [p.strip() for p in line.split('|')[1:-1]]

                if len(parts) >= 6:
                    peak_id = parts[0].strip()
                    label = parts[1].strip() if len(parts) > 1 else ""
                    position_str = parts[2].strip() if len(parts) > 2 else ""
                    fwhm_str = parts[3].strip() if len(parts) > 3 else ""
                    lg_str = parts[4].strip() if len(parts) > 4 else ""
                    area_str = parts[5].strip() if len(parts) > 5 else ""
                    model_str = parts[6].strip() if len(parts) > 6 else "SGL (Area)"

                    if peak_id and peak_id.isalpha() and len(peak_id) == 1:
                        try:
                            position = float(position_str.replace(',', '.'))
                            fwhm = float(fwhm_str.split('-')[0].replace(',', '.')) if fwhm_str and fwhm_str[0].isdigit() else 1.2
                            lg = float(lg_str.split('-')[0].split(':')[0]) if lg_str and lg_str[0].isdigit() else 20.0

                            current_peak = {
                                'id': peak_id,
                                'label': label,
                                'position': float(f"{position:.2f}"),
                                'fwhm': float(f"{fwhm:.2f}"),
                                'lg': float(f"{lg:.2f}"),
                                'model': model_str if model_str else "SGL (Area)",
                                'constraints': {}
                            }
                            self.suggested_peaks.append(current_peak)
                        except (ValueError, IndexError) as e:
                            print(f"DEBUG: Error parsing peak row: {e}, line: {line}")
                            continue

                    elif current_peak is not None and not peak_id:
                        current_peak['constraints'] = {
                            'position': position_str,
                            'fwhm': fwhm_str,
                            'lg': lg_str,
                            'area': area_str
                        }

        # Fallback: try old regex pattern if table parsing failed
        if not self.suggested_peaks:
            pattern = r'(\d+\.?\d*)\s*eV.*?FWHM[:\s]*(\d+\.?\d*)'
            for pos, fwhm in re.findall(pattern, result, re.I):
                self.suggested_peaks.append({
                    'id': chr(65 + len(self.suggested_peaks)),
                    'label': f"Peak {len(self.suggested_peaks) + 1}",
                    'position': float(pos),
                    'fwhm': float(fwhm),
                    'lg': 20.0,
                    'model': "SGL (Area)",
                    'constraints': {}
                })

        # If we have peaks but no background range, estimate from peak positions
        if self.suggested_peaks and not self.suggested_bg_range:
            positions = [p['position'] for p in self.suggested_peaks]
            min_pos = min(positions)
            max_pos = max(positions)
            self.suggested_bg_range = {
                'low': float(f"{min_pos - 5:.2f}"),
                'high': float(f"{max_pos + 5:.2f}")
            }
            print(f"DEBUG: Estimated background range from peaks: {self.suggested_bg_range['low']:.2f} - {self.suggested_bg_range['high']:.2f} eV")

        print(f"DEBUG: Parsed {len(self.suggested_peaks)} peaks from AI response")
        for p in self.suggested_peaks:
            print(f"  {p['id']}: {p['label']} at {p['position']} eV, FWHM={p['fwhm']}, constraints={p.get('constraints', {})}")

        # If in auto-fit mode and we parsed new peaks, show status
        if hasattr(self, 'auto_fit_mode') and self.auto_fit_mode and self.suggested_peaks:
            # Add a system message showing the parsed peaks on separate lines
            peaks_lines = [f"      - {p['id']}:{p['label']} @ {p['position']:.2f} eV" for p in self.suggested_peaks]
            peaks_summary = f"📋 Parsed {len(self.suggested_peaks)} peaks:\n" + "\n".join(peaks_lines)
            wx.CallAfter(self._append_chat, "system", peaks_summary)
            wx.CallAfter(self._append_chat, "system", "💡 Type 'yes' to apply, 'refit', 'bkg XXX YYY', 'auto bkg', describe changes, or 'cancel' to exit.")




        self.apply_btn.Enable(bool(self.suggested_peaks))

    def _enable_buttons(self, enable):
        self.identify_btn.Enable(enable)
        self.suggest_btn.Enable(enable)
        self.ask_btn.Enable(enable)
        self.auto_fit_btn.Enable(enable)

    def on_config(self, event):
        dlg = ConfigDialog(self, self.api_key, self.model,
                           self.auto_fit_loop_count, self.response_verbosity, self.send_images,
                           self.temperature, self.max_tokens)
        if dlg.ShowModal() == wx.ID_OK:
            (self.api_key, self.model, self.auto_fit_loop_count, self.response_verbosity,
             self.send_images, self.temperature, self.max_tokens) = dlg.get_values()
            self._save_config()
            self._update_status("Config saved", "green")
        dlg.Destroy()

    def on_clear_chat(self, event):
        self.chat_display.Clear()
        self.conversation_history = []
        self.element_context_sent = {}
        self._update_status("Chat cleared", "blue")


    def _get_messages_for_api(self):
        """Convert history to API format (for Claude)"""
        messages = []

        for msg in self.conversation_history:
            api_msg = {
                'role': msg['role'],
                'content': msg['content']
            }
            messages.append(api_msg)

        return messages

    def _add_to_history(self, role, content):
        """Add a message to conversation history"""
        message = {
            'role': role,
            'content': content,
            'timestamp': datetime.datetime.now().isoformat()
        }
        self.conversation_history.append(message)

    def _clear_history(self):
        """Clear conversation history and chat display"""
        self.conversation_history = []
        self.chat_display.Clear()
        self._update_status("New conversation started", "green")

    def save_conversation(self, filepath=None):
        """Save conversation to JSON file"""
        if not self.conversation_history:
            wx.MessageBox("No conversation to save", "Info", wx.OK | wx.ICON_INFORMATION)
            return

        if not filepath:
            dlg = wx.FileDialog(
                self, "Save Conversation",
                wildcard="JSON files (*.json)|*.json",
                style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT
            )
            if dlg.ShowModal() == wx.ID_CANCEL:
                return
            filepath = dlg.GetPath()

        conversation_data = {
            'created': datetime.datetime.now().isoformat(),
            'history': self.conversation_history
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(conversation_data, f, indent=2, default=str)

        self._update_status(f"Conversation saved to {os.path.basename(filepath)}", "green")

    def load_conversation(self, filepath=None):
        """Load conversation from JSON file"""
        if not filepath:
            # Get default load directory
            if hasattr(sys, '_MEIPASS'):
                # Running as exe
                default_dir = os.path.join(os.path.expanduser("~"), "Documents", "KherveFitting", "Conversations")
            else:
                # Running in development
                default_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "conversations")

            # Create directory if it doesn't exist
            os.makedirs(default_dir, exist_ok=True)

            dlg = wx.FileDialog(
                self, "Load Conversation",
                defaultDir=default_dir,
                wildcard="JSON files (*.json)|*.json",
                style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
            )
            if dlg.ShowModal() == wx.ID_CANCEL:
                return
            filepath = dlg.GetPath()

        with open(filepath, 'r', encoding='utf-8') as f:
            conversation_data = json.load(f)

        # Clear current state
        self.chat_display.Clear()
        self.conversation_history = []

        # Reload conversation history
        loaded_history = conversation_data['history']

        for msg in loaded_history:
            content = msg['content']
            role = msg['role']

            # Skip reference knowledge base messages (hidden from user display)
            if content.startswith('[Reference]') or content.startswith('Reference knowledge base:'):
                # Still add to history but don't display
                self.conversation_history.append(msg)
                continue
            if content.startswith('Loaded') and 'reference data' in content:
                self.conversation_history.append(msg)
                continue

            # Add to history
            self.conversation_history.append(msg)

            # Display in chat
            if role == 'user':
                self._append_chat('user', content)
            elif role == 'assistant':
                self._start_assistant_bubble()
                self._format_and_append_text(content)

        self._update_status(f"Conversation loaded from {os.path.basename(filepath)}", "green")

    def _export_as_text(self):
        """Export conversation as plain text file"""
        if not self.conversation_history:
            wx.MessageBox("No conversation to export", "Info", wx.OK | wx.ICON_INFORMATION)
            return

        dlg = wx.FileDialog(
            self, "Export Conversation",
            wildcard="Text files (*.txt)|*.txt",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT
        )
        if dlg.ShowModal() == wx.ID_CANCEL:
            return
        filepath = dlg.GetPath()

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("KherveAI Conversation Export\n")
            f.write(f"Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")

            for msg in self.conversation_history:
                role = "You" if msg['role'] == 'user' else "KherveAI"
                f.write(f"{role}:\n")
                f.write(msg['content'])
                f.write("\n\n" + "-" * 80 + "\n\n")

        self._update_status(f"Conversation exported to {os.path.basename(filepath)}", "green")

    def get_available_models(self):
        """Return static list of available GPT models"""
        self.model_load_status = "Using standard model list"
        return [
            "gpt-5.2",
            "gpt-5.1",
            "gpt-5",
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-4",
            "gpt-3.5-turbo",
            "o1",
            "o1-mini",
            "o3",
            "o3-mini"
        ]

    def get_available_models_OLD(self):
        """Fetch available GPT models from OpenAI API"""
        try:
            import openai
            api_key = getattr(self, 'api_key', None)
            if hasattr(self, 'panel') and hasattr(self.panel, 'api_key'):
                api_key = self.panel.api_key

            if not api_key:
                self.model_load_status = "⚠ No API key - using default list"
                return self.get_default_models()

            client = openai.OpenAI(api_key=api_key)
            models = client.models.list()

            # Filter for standard chat models only
            gpt_models = []
            for m in models.data:
                model_id = m.id

                # Skip specialized models
                if any(x in model_id for x in [
                    '-instruct', '-embedding', '-audio', '-realtime', '-search',
                    '-tts', '-whisper', '-transcribe', '-codex', '-pro', '-preview',
                    '-mini-tts', '-mini-audio', '-mini-search', '-mini-realtime',
                    '-mini-transcribe', '-chat-latest', '-codex-mini', '-codex-max',
                    '-search-api', '-nano'
                ]):
                    continue

                # Include only main chat models
                if model_id in ['gpt-5.2', 'gpt-5.1', 'gpt-5', 'gpt-5-mini',
                                'gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-4',
                                'gpt-3.5-turbo', 'o1', 'o1-mini', 'o3', 'o3-mini']:
                    gpt_models.append(model_id)

            gpt_models.sort(reverse=True)

            if gpt_models:
                self.model_load_status = f"✓ Loaded {len(gpt_models)} standard models"
                return gpt_models
            else:
                self.model_load_status = "⚠ No standard models found - using default list"
                return self.get_default_models()

        except Exception as e:
            self.model_load_status = f"✗ API failed: {str(e)[:50]}"
            print(f"Error fetching models: {e}")
            return self.get_default_models()

    def get_default_models(self):
        """Default model list if API call fails"""
        return [
            "gpt-5.2",
            "gpt-5.1",
            "gpt-5",
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-4",
            "gpt-3.5-turbo",
            "o1",
            "o1-mini",
            "o3",
            "o3-mini"
        ]


class ConfigDialog(wx.Dialog):
    """Configuration dialog"""

    def __init__(self, parent, api_key, model, loop_count=2, verbosity='Concise', send_images=False,
                 temperature=0.7, max_tokens=4000):
        super().__init__(parent, title="Configuration", size=(450, 520),
                         style=wx.DEFAULT_DIALOG_STYLE)

        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # API Key
        main_sizer.Add(wx.StaticText(panel, label="OpenAI API Key:"), 0, wx.LEFT | wx.TOP, 15)
        self.key_ctrl = wx.TextCtrl(panel, style=wx.TE_PASSWORD, size=(350, -1))
        self.key_ctrl.SetValue(api_key or "")
        main_sizer.Add(self.key_ctrl, 0, wx.LEFT | wx.RIGHT | wx.TOP, 15)

        # Model
        main_sizer.Add(wx.StaticText(panel, label="Model:"), 0, wx.LEFT | wx.TOP, 15)

        # Get available models from parent
        if hasattr(parent, 'get_available_models'):
            models = parent.get_available_models()
            status_text = getattr(parent, 'model_load_status', 'Using default model list')
        else:
            models = self.get_default_models()
            status_text = 'Using default model list'

        self.model_choice = wx.Choice(panel, choices=models)
        self.model_choice.SetSelection(models.index(model) if model in models else 0)
        main_sizer.Add(self.model_choice, 0, wx.LEFT | wx.TOP, 15)

        # Add status label
        self.status_label = wx.StaticText(panel, label=status_text)
        if '✗' in status_text:
            self.status_label.SetForegroundColour(wx.RED)
        elif '✓' in status_text:
            self.status_label.SetForegroundColour(wx.Colour(0, 128, 0))
        else:
            self.status_label.SetForegroundColour(wx.BLUE)
        main_sizer.Add(self.status_label, 0, wx.LEFT | wx.TOP, 5)

        # Store models list for get_values
        self.models_list = models

        # Separator
        main_sizer.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.ALL, 10)

        # API Settings section
        api_label = wx.StaticText(panel, label="API Settings:")
        api_label.SetFont(api_label.GetFont().Bold())
        main_sizer.Add(api_label, 0, wx.LEFT, 15)

        # Temperature
        temp_sizer = wx.BoxSizer(wx.HORIZONTAL)
        temp_sizer.Add(wx.StaticText(panel, label="Temperature:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        self.temp_spin = wx.SpinCtrlDouble(panel, value=str(temperature), min=0.0, max=2.0, inc=0.1, size=(70, -1))
        self.temp_spin.SetDigits(1)
        self.temp_spin.SetToolTip("Controls randomness: 0.0 = deterministic, 1.0 = creative, 2.0 = very random")
        temp_sizer.Add(self.temp_spin, 0, wx.ALIGN_CENTER_VERTICAL)
        temp_sizer.Add(wx.StaticText(panel, label="(0.0-2.0)"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5)
        main_sizer.Add(temp_sizer, 0, wx.LEFT | wx.TOP, 15)

        # Max Tokens
        token_sizer = wx.BoxSizer(wx.HORIZONTAL)
        token_sizer.Add(wx.StaticText(panel, label="Max tokens:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        self.token_spin = wx.SpinCtrl(panel, value=str(max_tokens), min=500, max=16000, size=(80, -1))
        self.token_spin.SetToolTip("Maximum response length (500-16000 tokens)")
        token_sizer.Add(self.token_spin, 0, wx.ALIGN_CENTER_VERTICAL)
        token_sizer.Add(wx.StaticText(panel, label="(500-16000)"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5)
        main_sizer.Add(token_sizer, 0, wx.LEFT | wx.TOP, 15)

        # Separator
        main_sizer.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.ALL, 10)

        # Auto-Fit Settings section
        settings_label = wx.StaticText(panel, label="Auto-Fit Settings:")
        settings_label.SetFont(settings_label.GetFont().Bold())
        main_sizer.Add(settings_label, 0, wx.LEFT, 15)

        # Loop count
        loop_sizer = wx.BoxSizer(wx.HORIZONTAL)
        loop_sizer.Add(wx.StaticText(panel, label="Refinement loops:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        self.loop_spin = wx.SpinCtrl(panel, value=str(loop_count), min=1, max=10, size=(60, -1))
        self.loop_spin.SetToolTip("Number of auto-refinement iterations after applying fit")
        loop_sizer.Add(self.loop_spin, 0, wx.ALIGN_CENTER_VERTICAL)
        main_sizer.Add(loop_sizer, 0, wx.LEFT | wx.TOP, 15)

        # Verbosity
        verb_sizer = wx.BoxSizer(wx.HORIZONTAL)
        verb_sizer.Add(wx.StaticText(panel, label="Response style:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        self.verbosity_combo = wx.ComboBox(panel, choices=["Concise", "Normal", "Extended"],
                                           style=wx.CB_READONLY, size=(100, -1))
        verbosity_index = ["Concise", "Normal", "Extended"].index(verbosity) if verbosity in ["Concise", "Normal", "Extended"] else 0
        self.verbosity_combo.SetSelection(verbosity_index)
        self.verbosity_combo.SetToolTip("AI response detail level")
        verb_sizer.Add(self.verbosity_combo, 0, wx.ALIGN_CENTER_VERTICAL)
        main_sizer.Add(verb_sizer, 0, wx.LEFT | wx.TOP, 15)

        # Send images checkbox
        self.send_images_cb = wx.CheckBox(panel, label="Send plot screenshots to AI for analysis")
        self.send_images_cb.SetValue(send_images)
        self.send_images_cb.SetToolTip("Enable to have AI visually inspect your plots (requires gpt-4o)")
        main_sizer.Add(self.send_images_cb, 0, wx.LEFT | wx.TOP, 15)

        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        save_btn = wx.Button(panel, wx.ID_OK, "Save")
        cancel_btn = wx.Button(panel, wx.ID_CANCEL, "Cancel")
        btn_sizer.Add(save_btn, 0, wx.RIGHT, 10)
        btn_sizer.Add(cancel_btn, 0)
        main_sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.ALL, 20)

        panel.SetSizer(main_sizer)
        self.Centre()

    def get_values(self):
        return (
            self.key_ctrl.GetValue().strip(),
            self.models_list[self.model_choice.GetSelection()],
            self.loop_spin.GetValue(),
            self.verbosity_combo.GetValue(),
            self.send_images_cb.GetValue(),
            self.temp_spin.GetValue(),
            self.token_spin.GetValue()
        )

    def get_default_models(self):
        """Default model list if API call fails"""
        return [
            "gpt-5.2",
            "gpt-5.1",
            "gpt-5",
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-4",
            "gpt-3.5-turbo",
            "o1",
            "o1-mini",
            "o3",
            "o3-mini"
        ]


def open_xps_assistant(parent, window):
    """Open the XPS Assistant - call this from Widgets_Toolbars.py"""
    frame = XPSAssistantFrame(parent, window)
    frame.Show()
    return frame