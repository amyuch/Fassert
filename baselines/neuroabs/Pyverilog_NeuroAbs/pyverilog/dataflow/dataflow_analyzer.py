# -------------------------------------------------------------------------------
# dataflow_analyzer.py
#
# Verilog module signal/module dataflow analyzer
#
# Copyright (C) 2013, Shinya Takamaeda-Yamazaki
# License: Apache 2.0
# -------------------------------------------------------------------------------
from __future__ import absolute_import
from __future__ import print_function
import sys
import os
from pyverilog.vparser.ast import Assign
from pyverilog.vparser.parser import VerilogCodeParser
from pyverilog.dataflow.modulevisitor import ModuleVisitor
from pyverilog.dataflow.signalvisitor import SignalVisitor
from pyverilog.dataflow.bindvisitor import BindVisitor

# Increasing the maximum recursion size for deeper traversal
sys.setrecursionlimit(16 * 1024)


class VerilogDataflowAnalyzer(VerilogCodeParser):
    def __init__(self, filelist, topmodule='TOP', noreorder=False, nobind=False,
                 preprocess_include=None,
                 preprocess_define=None):
        self.topmodule = topmodule
        self.terms = {}
        self.binddict = {}
        self.line_map = {}
        self.instance_map = {}
        self.signal_width = {}
        self.module_map = {}
        self.frametable = None
        files = filelist if isinstance(filelist, tuple) or isinstance(
            filelist, list) else [filelist]
        VerilogCodeParser.__init__(self, files,
                                   preprocess_include=preprocess_include,
                                   preprocess_define=preprocess_define)
        self.noreorder = noreorder
        self.nobind = nobind

    def generate(self):
        ast = self.parse()

        module_visitor = ModuleVisitor()
        module_visitor.visit(ast)
        modulenames = module_visitor.get_modulenames()
        moduleinfotable = module_visitor.get_moduleinfotable()
        self.instance_map = module_visitor.get_instance_map()
        signal_visitor = SignalVisitor(moduleinfotable, self.topmodule)
        signal_visitor.start_visit()
        frametable = signal_visitor.getFrameTable()
        self.obtain_signal_width(signal_visitor)
        self.get_module_lines(moduleinfotable)
                
        # print(self.signal_width)
        if self.nobind:
            self.frametable = frametable
            return

        bind_visitor = BindVisitor(moduleinfotable, self.topmodule, frametable,
                                   noreorder=self.noreorder)

        bind_visitor.start_visit()
        dataflow = bind_visitor.getDataflows()
        self.line_map = bind_visitor.get_linemap()
        
        print(self.line_map)
        self.frametable = bind_visitor.getFrameTable()
        self.terms = dataflow.getTerms()
        self.binddict = dataflow.getBinddict()

    def get_module_lines(self, moduleinfotable):
        for name, info in  moduleinfotable.dict.items():
            start_line = info.definition.lineno
            self.module_map[start_line] = info.name

    def obtain_signal_width(self, signal_visitor):
        for block, listing in signal_visitor.moduleinfotable.dict.items():
            for  signal_name, info in listing.variables.signal.dict.items():
                for information in info:
                    if information.width is None:
                        self.signal_width[signal_name] = 1
                    else:
                        if hasattr(information.width.msb, 'value'):
                            msb = int(information.width.msb.value)  
                            para = None
                        else:
                            msb_info = information.width.msb
                            var = msb_info.left
                            var_val = int(listing.variables.const.dict[var.name][0].value.var.value)
                            msb = var_val -1 
                            para = var.name
                        
                        self.signal_width[signal_name] = msb - int(information.width.lsb.value) + 1
            
            for  signal_name, info in listing.variables.const.dict.items():
                for information in info:
                    if information.width is None:
                        self.signal_width[signal_name] = 1
                    else:
                        if hasattr(information.width.msb, 'value'):
                            msb = int(information.width.msb.value)  
                            para = None
                        else:
                            msb_info = information.width.msb
                            var = msb_info.left
                            var_val = int(listing.variables.const.dict[var.name][0].value.var.value)
                            msb = var_val -1 
                            para = var.name
                        
                        self.signal_width[signal_name] = msb - int(information.width.lsb.value) + 1            
            
            for  lines in listing.definition.items:
                # if(lines.lineno ==5213):
                #     print(lines.lineno )
                if hasattr(lines, 'list') == False:
                    continue
                for information in lines.list:
                    if isinstance(information, Assign):
                        continue
                    if information.width is None:
                        self.signal_width[information.name] = 1
                    else:
                        if hasattr(information.width.msb, 'value'):
                            msb = int(information.width.msb.value)  
                        else:
                            msb_info = information.width.msb
                            var = msb_info.left
                            var_val = int(listing.variables.const.dict[var.name][0].value.var.value)
                            msb = var_val -1 
                        
                        self.signal_width[information.name] = msb - int(information.width.lsb.value) + 1  
                        
                        
    def getFrameTable(self):
        return self.frametable

    # -------------------------------------------------------------------------
    def getInstances(self):
        if self.frametable is None:
            return ()
        return self.frametable.getAllInstances()

    def getSignals(self):
        if self.frametable is None:
            return ()
        return self.frametable.getAllSignals()

    def getConsts(self):
        if self.frametable is None:
            return ()
        return self.frametable.getAllConsts()

    def getTerms(self):
        return self.terms

    def getBinddict(self):
        return self.binddict
