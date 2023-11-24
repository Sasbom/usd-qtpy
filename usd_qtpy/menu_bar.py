# Abstraction for a top menubar
import logging

from qtpy import QtCore, QtWidgets
from functools import partial

class MenuWrapper:
    def __init__(self, name : str):
        """
        init method. 
        Callbacks are stored seperately so that they may be modified at a later date,
        or flexibly generated dependent on context.
        """
        self._menu = QtWidgets.QMenu()
        self._callbacks = {} # dict{str (label) : tuple(QAction, callback)}
        self._name = name

    @property
    def containedMenu(self):
        return self._menu

    @property
    def name(self):
        return self._name
    
    def registerAction(self,item_name : str, callback : partial):
        """
        Register an action to the menu, if the key is not present.
        Callbacks are to be constructed using functools.partial,
        and have to return nothing.
        """
        if item_name in self._callbacks.keys():
            logging.warning(f"Menu {self._name} already has an action registered as {item_name}")
            return
        
        action = self._menu.addAction(item_name)
        action.triggered.connect(lambda : callback())
        self._callbacks[item_name] = (action,callback)

    def modifyAction(self,item_name : str, callback : partial):
        """
        Register an action to the menu, if the key is not present.
        Callbacks are to be constructed using functools.partial.
        """
        if item_name not in self._callbacks.keys():
            logging.warning(f"Menu {self._name} does not have anything registered as {item_name}")
            return
        
        action = self._menu.addAction(item_name)
        action.triggered.connect(lambda : callback())
        self._callbacks[item_name] = (action,callback)

    def removeAction(self,item_name : str):
        if item_name not in self._callbacks.keys():
            logging.warning(f"Menu {self._name} does not have anything registered as {item_name}")
            return
        
        self._menu.removeAction(self._callbacks[item_name][0])
        self._callbacks.pop(item_name)

    def clearMenu(self):
        self._menu.clear()
        self._callbacks = {}

    
class MenuBarWrapper:
    def __init__(self): 
        self._bar = QtWidgets.QMenuBar()
        self._menus = {} # dict{str : MenuWrapper}

    def applyToLayout(self,layout):
        """
        applies menubar to any given layout
        """
        layout.setMenuBar(self._bar)

    def registerMenu(self, menuwrapper : MenuWrapper):
        if menuwrapper.name in self._menus.keys():
            logging.warning(f"Menu bar already has key {menuwrapper.name}, no duplicates allowed")
            return
        
        self._menus[menuwrapper.name] : MenuWrapper = menuwrapper.containedMenu
        action = self._bar.addAction(menuwrapper.name)
        action.setMenu(menuwrapper.containedMenu)

    def removeMenu(self, menuwrapper : MenuWrapper):
        if menuwrapper.name not in self._menus.keys():
            logging.warning(f"Menu {menuwrapper.name} not present in menu bar")
            return

        self._menus.pop(menuwrapper.name)
        self._bar.clear()

        for menu in self._menus:
            self.registerMenu(menu)

    def clearMenuBar(self):
        self._menus = {}
        self._bar.clear()


    def getMenu(self,key : str):
        try:
            return self._menus[key]
        except Exception as e:
            logging.warning(f"Menu {key} not present in menu bar")
            return