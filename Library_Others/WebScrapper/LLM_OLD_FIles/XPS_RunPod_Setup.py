# XPS_RunPod_Setup.py - Setup dialog for RunPod
# Location: libraries/LLMs/XPS_RunPod_Setup.py

import wx
import threading


class RunPodConfigDialog(wx.Dialog):
    """Configuration dialog for RunPod endpoint"""

    def __init__(self, parent, runpod_assistant):
        super().__init__(parent, title="RunPod Configuration", size=(500, 300))
        self.runpod = runpod_assistant

        self._create_ui()

    def _create_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Instructions
        intro = wx.StaticText(panel, label="""
Configure your RunPod vLLM endpoint.
Your Endpoint ID is in the RunPod URL (e.g., csm00w7zi50onw)
        """)
        sizer.Add(intro, 0, wx.ALL, 10)

        # API Key
        sizer.Add(wx.StaticText(panel, label="RunPod API Key:"), 0, wx.LEFT | wx.TOP, 10)
        self.api_key_ctrl = wx.TextCtrl(panel, style=wx.TE_PASSWORD, size=(450, -1))
        self.api_key_ctrl.SetHint("Your RunPod API key")
        if self.runpod.api_key:
            self.api_key_ctrl.SetValue(self.runpod.api_key)
        sizer.Add(self.api_key_ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # Endpoint ID
        sizer.Add(wx.StaticText(panel, label="Endpoint ID:"), 0, wx.LEFT | wx.TOP, 10)
        self.endpoint_ctrl = wx.TextCtrl(panel, size=(450, -1))
        self.endpoint_ctrl.SetHint("e.g., csm00w7zi50onw")
        if self.runpod.endpoint_id:
            self.endpoint_ctrl.SetValue(self.runpod.endpoint_id)
        sizer.Add(self.endpoint_ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # Test button and status
        test_row = wx.BoxSizer(wx.HORIZONTAL)
        self.test_btn = wx.Button(panel, label="Test Connection")
        self.test_btn.Bind(wx.EVT_BUTTON, self.on_test)
        test_row.Add(self.test_btn, 0, wx.RIGHT, 10)

        self.status_label = wx.StaticText(panel, label="")
        test_row.Add(self.status_label, 0, wx.ALIGN_CENTER_VERTICAL)

        sizer.Add(test_row, 0, wx.ALL, 10)

        # Buttons
        btn_sizer = wx.StdDialogButtonSizer()
        ok_btn = wx.Button(panel, wx.ID_OK, "Save")
        cancel_btn = wx.Button(panel, wx.ID_CANCEL)
        btn_sizer.AddButton(ok_btn)
        btn_sizer.AddButton(cancel_btn)
        btn_sizer.Realize()
        sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.ALL, 10)

        panel.SetSizer(sizer)

    def on_test(self, event):
        """Test connection"""
        api_key = self.api_key_ctrl.GetValue().strip()
        endpoint_id = self.endpoint_ctrl.GetValue().strip()

        if not api_key or not endpoint_id:
            self.status_label.SetLabel("Enter API key and Endpoint ID")
            self.status_label.SetForegroundColour(wx.Colour(200, 0, 0))
            return

        self.status_label.SetLabel("Testing...")
        self.status_label.SetForegroundColour(wx.Colour(0, 0, 150))
        self.test_btn.Enable(False)

        def test():
            # Temporarily set values
            self.runpod.api_key = api_key
            self.runpod.endpoint_id = endpoint_id
            self.runpod.base_url = f"https://api.runpod.ai/v2/{endpoint_id}"

            success, msg = self.runpod.test_connection()
            wx.CallAfter(self.show_test_result, success, msg)

        thread = threading.Thread(target=test)
        thread.daemon = True
        thread.start()

    def show_test_result(self, success, msg):
        """Show test result"""
        self.test_btn.Enable(True)
        if success:
            self.status_label.SetLabel("✓ Connected!")
            self.status_label.SetForegroundColour(wx.Colour(0, 128, 0))
        else:
            self.status_label.SetLabel(f"✗ Failed: {msg}")
            self.status_label.SetForegroundColour(wx.Colour(200, 0, 0))

    def get_values(self):
        """Get entered values"""
        return (
            self.api_key_ctrl.GetValue().strip(),
            self.endpoint_ctrl.GetValue().strip()
        )