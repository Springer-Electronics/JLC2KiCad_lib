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


OUTPUT_DIR = "JLC2KiCad_lib"
FOOTPRINT_LIB  = "footprint"
FOOTPRINT_LIB_NICK  = "jlc"  #set the same as FOOTPRINT_LIB, or to nickname choosen in Footprint libraries manager
SYMBOL_LIB = "default_lib"
SYMBOL_LIB_DIR = "symbol"


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

    def IsVersion(self, VersionStr):
        for v in VersionStr:
            if v in self.kicad_build_version:
                return True
        return False


    def Run(self):
        board: pcbnew.BOARD = pcbnew.GetBoard()
        board_dir = os.path.dirname(board.GetFileName())

        if self._pcbnew_frame is None:
            try:
                self._pcbnew_frame = [x for x in wx.GetTopLevelWindows() if ('pcbnew' in x.GetTitle().lower() and not 'python' in x.GetTitle().lower()) or ('pcb editor' in x.GetTitle().lower())]
                if len(self._pcbnew_frame) == 1:
                    self._pcbnew_frame = self._pcbnew_frame[0]
                else:
                    self._pcbnew_frame = None
            except:
                pass

        jlc_prompt = wx.TextEntryDialog(None, "JLCPCB part", value="", caption="Download footprint")
        if(jlc_prompt.ShowModal() == wx.ID_CANCEL):
            return
        component_id = jlc_prompt.GetValue()
        if not component_id:
            return


        logging.info(f"creating library for component {component_id}")
        data = json.loads(
            requests.get(
                f"https://easyeda.com/api/products/{component_id}/svgs"
            ).content.decode()
        )

        if not data["success"]:
            logging.error(
                f"failed to get component uuid for {component_id}\nThe component # is probably wrong. Check a possible typo and that the component exists on easyEDA"
            )
            return ()
        footprint_component_uuid = data["result"][-1]["component_uuid"]
        symbol_component_uuid = [i["component_uuid"] for i in data["result"][:-1]]

        footprint_name, datasheet_link = create_footprint(
            footprint_component_uuid=footprint_component_uuid,
            component_id=component_id,
            footprint_lib=FOOTPRINT_LIB,
            output_dir=os.path.join(board_dir, OUTPUT_DIR),
            model_base_variable="",
            model_dir="packages3d",
            skip_existing=True,
            models="STEP",
        )

        create_symbol(
            symbol_component_uuid=symbol_component_uuid,
            footprint_name=footprint_name.replace(FOOTPRINT_LIB, FOOTPRINT_LIB_NICK) #link footprint according to the nickname
                .replace(".pretty", ""),  # see https://github.com/TousstNicolas/JLC2KiCad_lib/issues/47
            datasheet_link=datasheet_link,
            library_name=SYMBOL_LIB,
            symbol_path=SYMBOL_LIB_DIR,
            output_dir=os.path.join(board_dir, OUTPUT_DIR),
            component_id=component_id,
            skip_existing=False,
        )

        
        libpath = os.path.join(board_dir, OUTPUT_DIR, FOOTPRINT_LIB)
        component_name = footprint_name.replace(FOOTPRINT_LIB + ":", "")

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



        # Footprint string pasting based on KiBuzzard https://github.com/gregdavill/KiBuzzard/blob/main/KiBuzzard/plugin.py
        if self.IsVersion(['5.99','6.', '7.']):
            if self._pcbnew_frame is not None:
                # Set focus to main window and attempt to execute a Paste operation 
                try:
                    evt = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
                    evt.SetKeyCode(ord('V'))
                    #evt.SetUnicodeKey(ord('V'))
                    evt.SetControlDown(True)
                    self.logger.log(logging.INFO, "Using wx.KeyEvent for paste")
            
                    wnd = [i for i in self._pcbnew_frame.Children if i.ClassName == 'wxWindow'][0]

                    self.logger.log(logging.INFO, " Injecting event: {} into window: {}".format(evt, wnd))
                    wx.PostEvent(wnd, evt)
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