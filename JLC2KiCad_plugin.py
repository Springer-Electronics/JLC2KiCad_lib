#!/usr/bin/env python
import pcbnew
import os
import wx

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


    def Run(self):
        board: pcbnew.BOARD = pcbnew.GetBoard()
        board_dir = os.path.dirname(board.GetFileName())


        jlc_prompt = wx.TextEntryDialog(None, "JLCPCB part", value="", caption="Download footprint")
        if(jlc_prompt.ShowModal() == wx.ID_CANCEL):
            return
        component_id = jlc_prompt.GetValue()
        if not component_id:
            return

        import requests
        import json
        import logging

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
        fp : pcbnew.FOOTPRINT = pcbnew.FootprintLoad(libpath, component_name)
        fp.SetPosition(pcbnew.VECTOR2I(0, 0))
        board.Add(fp)
        pcbnew.Refresh()
        wx.MessageBox("Footprint " + component_name + " was placed in top left corner")

        try:
            pcbnew.FocusOnItem(fp)

            self._pcbnew_frame = [x for x in wx.GetTopLevelWindows() if ('pcbnew' in x.GetTitle().lower() and 'python' not in x.GetTitle().lower()) or ('pcb editor' in x.GetTitle().lower())]
            if len(self._pcbnew_frame) == 1:
                self._pcbnew_frame = self._pcbnew_frame[0]
            
                wnd = [i for i in self._pcbnew_frame.Children if i.ClassName == 'wxWindow'][0]
                evt = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
                evt.SetKeyCode(ord('m'))  #not reliable - it will move also footprint that was previously selected
                wx.PostEvent(wnd, evt)
        except:
            #kicad 7 doesn't have FocusOnItem() method
            pass