#!/usr/bin/env python
import sys
import pcbnew
import os
import wx
import logging
import tempfile
import requests
import json

from .JLC2KiCadLib.footprint.footprint import create_footprint
from .JLC2KiCadLib.symbol.symbol import create_symbol


OUTPUT_FOLDER = "JLC2KiCad_lib"
FOOTPRINT_LIB  = "footprint"
FOOTPRINT_LIB_NICK  = "jlc"  #set the same as FOOTPRINT_LIB, or to nickname choosen in Footprint libraries manager
SYMBOL_LIB = "default_lib"
SYMBOL_LIB_DIR = "symbol"


class MyCustomDialog(wx.Dialog):
    def __init__(self, parent, title, message, caption):
        super(MyCustomDialog, self).__init__(parent, title=title, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        # Create a sizer to manage the layout
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Add a message label
        sizer.Add(wx.StaticText(self, label=message), 0, wx.ALL, 10)

        # Add a text entry field
        self.text_entry = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        sizer.Add(self.text_entry, 0, wx.ALL | wx.EXPAND, 10)

        # Add custom buttons
        box = wx.StdDialogButtonSizer()
        
        box.AddButton(wx.Button(self, wx.ID_APPLY, "Download to project library"))
        ok_button = wx.Button(self, wx.ID_OK, "Copy to clipboard")
        box.AddButton(ok_button)
        box.AddButton(wx.Button(self, wx.ID_CANCEL, "Cancel"))
        box.AddButton(wx.Button(self, wx.ID_HELP, "Help"))
        
        box.Realize()

        sizer.Add(box, 0, wx.ALL | wx.EXPAND, 10)

        self.SetSizer(sizer)
        self.Fit()

        self.Bind(wx.EVT_BUTTON, self.OnDownload, id=wx.ID_APPLY)
        self.Bind(wx.EVT_BUTTON, self.OnPlaceFootprint, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.OnCancel, id=wx.ID_CANCEL)
        self.Bind(wx.EVT_BUTTON, self.OnHelp, id=wx.ID_HELP)

        
        self.SetDefaultItem(ok_button)


    def OnDownload(self, event):
        component_id = self.text_entry.GetValue()
        if not component_id:
            wx.MessageBox("Type part number, e.g. C326215")
            return
        board: pcbnew.BOARD = pcbnew.GetBoard()
        board_dir = os.path.dirname(board.GetFileName())
        self.libpath, self.component_name = download_part(component_id, os.path.join(board_dir, OUTPUT_FOLDER), True, True)
        wx.MessageBox(f"Footprint " + self.component_name + " downloaded to project library " + self.libpath)

    def OnPlaceFootprint(self, event):
        component_id = self.text_entry.GetValue()
        if not component_id:
            wx.MessageBox("Type part number, e.g. C326215")
            return
        out_dir =  os.path.join(tempfile.mkdtemp())
        self.libpath, self.component_name = download_part(component_id, out_dir)
        self.EndModal(wx.ID_OK)

    def OnCancel(self, event):
        self.EndModal(wx.ID_CANCEL)

    def OnHelp(self, event):
        wx.MessageBox("Test button download footprint to temporary folder and then pastes to the PCB. If paste didn't work, press Ctrl+V.\nDownloading to project uses JLC2KiCad_lib library folder in the project path", "Help", wx.OK | wx.ICON_INFORMATION)


def download_part(component_id, out_dir, get_symbol=False, skip_existing=False):
    logging.info(f"creating library for component {component_id}")
    data = json.loads(
        requests.get(
            f"https://easyeda.com/api/products/{component_id}/svgs"
        ).content.decode()
    )

    if not data["success"]:
        wx.MessageBox(
            f"Failed to get component uuid for {component_id}\nThe component # is probably wrong. Check a possible typo and that the component exists on easyEDA"
        )
        return "", ""
    
    footprint_component_uuid = data["result"][-1]["component_uuid"]
    footprint_name, datasheet_link = create_footprint(
        footprint_component_uuid=footprint_component_uuid,
        component_id=component_id,
        footprint_lib=FOOTPRINT_LIB,
        output_dir=out_dir,
        model_base_variable="",
        model_dir="packages3d",
        skip_existing=skip_existing,
        models="STEP",
    )

    if get_symbol:
        symbol_component_uuid = [i["component_uuid"] for i in data["result"][:-1]]
        create_symbol(
            symbol_component_uuid=symbol_component_uuid,
            footprint_name=footprint_name.replace(FOOTPRINT_LIB, FOOTPRINT_LIB_NICK) #link footprint according to the nickname
                .replace(".pretty", ""),  # see https://github.com/TousstNicolas/JLC2KiCad_lib/issues/47
            datasheet_link=datasheet_link,
            library_name=SYMBOL_LIB,
            symbol_path=SYMBOL_LIB_DIR,
            output_dir=out_dir,
            component_id=component_id,
            skip_existing=skip_existing,
        )
    libpath = os.path.join(out_dir, FOOTPRINT_LIB)
    component_name = footprint_name.replace(FOOTPRINT_LIB + ":", "")
    
    return libpath, component_name

class JLC2KiCad_GUI(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = "Downlaod JLC part"
        self.category = "Modify PCB"
        self.description = "A description of the plugin and what it does"
        self.show_toolbar_button = True
 
        self.pcbnew_icon_support = hasattr(self, "show_toolbar_button")
        icon_dir = os.path.join(os.path.dirname(__file__), "images")
        self.icon_file_name = os.path.join(icon_dir, 'icon.png')
        
        self._pcbnew_frame = None
        self.kicad_build_version = pcbnew.GetBuildVersion()

        self.InitLogger()
        self.logger = logging.getLogger(__name__)

    def IsVersion(self, version):
        for v in version:
            if v in self.kicad_build_version:
                return True
        return False

    def PasteFootprint(self):
        # Footprint string pasting based on KiBuzzard https://github.com/gregdavill/KiBuzzard/blob/main/KiBuzzard/plugin.py
        if self.IsVersion(['5.99','6.', '7.']):
            if self._pcbnew_frame is not None:
                # Set focus to main window and attempt to execute a Paste operation 
                wx.MilliSleep(100)
                try:
                    # Send ESC key before Ctrl+V to close other activities
                    esc_evt = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
                    esc_evt.SetKeyCode(wx.WXK_ESCAPE)
                    self.logger.log(logging.INFO, "Using wx.KeyEvent for ESC key")

                    wnd = [i for i in self._pcbnew_frame.Children if i.ClassName == 'wxWindow'][0]
                    self.logger.log(logging.INFO, "Injecting ESC event: {} into window: {}".format(esc_evt, wnd))
                    wx.PostEvent(wnd, esc_evt)

                    # Simulate pressing Ctrl+V to paste footprint
                    v_evt = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
                    v_evt.SetKeyCode(ord('V'))
                    v_evt.SetControlDown(True)
                    self.logger.log(logging.INFO, "Using wx.KeyEvent for Ctrl+V")

                    self.logger.log(logging.INFO, "Injecting Ctrl+V event: {} into window: {}".format(v_evt, wnd))
                    wx.PostEvent(wnd, v_evt)

                except:
                    # Likely on Linux with old wx python support :(
                    self.logger.log(logging.INFO, "Using wx.UIActionSimulator for paste")
                    keyinput = wx.UIActionSimulator()
                    self._pcbnew_frame.Raise()
                    self._pcbnew_frame.SetFocus()
                    wx.MilliSleep(100)
                    wx.Yield()
                    # Press and release CTRL + V
                    keyinput.Char(ord("V"), wx.MOD_CONTROL)
                    wx.MilliSleep(100)
            else:
                self.logger.log(logging.ERROR, "No pcbnew window found")
        else:
            self.logger.log(logging.ERROR, "Version check failed \"{}\" not in version list".format(self.kicad_build_version))

    def Run(self):
        board: pcbnew.BOARD = pcbnew.GetBoard()

        if self._pcbnew_frame is None:
            try:
                self._pcbnew_frame = [x for x in wx.GetTopLevelWindows() if ('pcbnew' in x.GetTitle().lower() and not 'python' in x.GetTitle().lower()) or ('pcb editor' in x.GetTitle().lower())]
                if len(self._pcbnew_frame) == 1:
                    self._pcbnew_frame = self._pcbnew_frame[0]
                else:
                    self._pcbnew_frame = None
            except:
                pass

        part_download_dialog = MyCustomDialog(None, "Download JLCPCB part footprint and symbol", "JLCPCB part no:", "JLCPCB part download plugin")
        part_download_dialog.Center()
        
        dialog_answer = part_download_dialog.ShowModal()
        if dialog_answer == wx.ID_CANCEL:
            return
        if dialog_answer == wx.ID_OK:
            libpath = part_download_dialog.libpath
            component_name = part_download_dialog.component_name
            if component_name:
                self.logger.log(logging.DEBUG, "Loading footprint into the clipboard")
                clipboard = wx.Clipboard.Get()
                if clipboard.Open():
                    # read file
                    with open(os.path.join(libpath, component_name + ".kicad_mod"), 'r') as file:
                        footprint_string = file.read()
                    clipboard.SetData(wx.TextDataObject(footprint_string))
                    clipboard.Close()
                else:
                    self.logger.log(logging.DEBUG, "Clipboard error")
                    fp : pcbnew.FOOTPRINT = pcbnew.FootprintLoad(libpath, component_name)
                    fp.SetPosition(pcbnew.VECTOR2I(0, 0))
                    board.Add(fp)
                    pcbnew.Refresh()
                    wx.MessageBox("Clipboard couldn't be opened. Footprint " + component_name + " was placed in top left corner of the canvas")

                self.PasteFootprint()



    def InitLogger(self):
        root = logging.getLogger()
        root.setLevel(logging.DEBUG)

        # Log to stderr
        handler1 = logging.StreamHandler(sys.stderr)
        handler1.setLevel(logging.DEBUG)


        log_path = os.path.dirname(__file__)
        log_file = os.path.join(log_path, "JLC2KiCad_plugin.log")

        # and to our error file
        # Check logging file permissions, if fails, move log file to tmp folder
        handler2 = None
        try:
            handler2 = logging.FileHandler(log_file)
        except PermissionError:
            log_path = os.path.join(tempfile.mkdtemp()) 
            try: # Use try/except here because python 2.7 doesn't support exist_ok
                os.makedirs(log_path)

            except:
                pass
            log_file = os.path.join(log_path, "JLC2KiCad_plugin.log")
            handler2 = logging.FileHandler(log_file)

            # Also move config file
            self.config_file = os.path.join(log_path, 'config.json')
        
        handler2.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "%(asctime)s %(name)s %(lineno)d:%(message)s", datefmt="%m-%d %H:%M:%S"
        )
        handler1.setFormatter(formatter)
        handler2.setFormatter(formatter)
        root.addHandler(handler1)
        root.addHandler(handler2)