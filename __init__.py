from __future__ import print_function
import pprint
import traceback
import sys

try:
	print("Starting kidiff")
	from .JLC2KiCad_plugin import JLC2KiCad_GUI
	JLC2KiCad_GUI().register()
except Exception as e:
	traceback.print_exc(file=sys.stdout)
	pprint.pprint(e)
