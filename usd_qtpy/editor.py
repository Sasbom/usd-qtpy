import logging

from qtpy import QtWidgets

from . import (
    prim_hierarchy,
    layer_editor,
    prim_spec_editor,
    menu_bar
)

from functools import partial

try:
    from usd_qtpy import viewer
    HAS_VIEWER = True
except ImportError:
    logging.warning("Unable to import usdview dependencies, skipping view..")
    HAS_VIEWER = False


class EditorWindow(QtWidgets.QDialog):
    """Example editor window containing the available components."""
    def __init__(self, stage, parent=None):
        super(EditorWindow, self).__init__(parent=parent)

        self.setWindowTitle("USD Editor")

        layout = QtWidgets.QVBoxLayout(self)

        
        bar = menu_bar.MenuBarWrapper()
        
        testmenu = menu_bar.MenuWrapper("Test...")
        action1 = partial(print,"Menu item 1")
        testmenu.registerAction("Item 1", action1)

        bar.registerMenu(testmenu)

        bar.applyToLayout(layout)

        ## Testing zone begin

        #toolbar = QtWidgets.QMenuBar()

        #menu1 = QtWidgets.QMenu()
        #item1_action = menu1.addAction("item1")
        #menu1.addAction("item2")

        #callback = lambda : print("wowowowow")

        #item1_action.triggered.connect(lambda: callback())
        #callback = lambda : print("wowiezowie")

        #test_baritem = toolbar.addAction("menu1")
        #test_baritem.setMenu(menu1)

        #layout.setMenuBar(toolbar)

        ## Testing zone end


        splitter = QtWidgets.QSplitter(self)
        layout.addWidget(splitter)

        layer_tree_widget = layer_editor.LayerTreeWidget(
            stage=stage,
            include_session_layer=False,
            parent=self
        )
        splitter.addWidget(layer_tree_widget)

        hierarchy_widget = prim_hierarchy.HierarchyWidget(stage=stage)
        splitter.addWidget(hierarchy_widget)

        if HAS_VIEWER:
            viewer_widget = viewer.Widget(stage=stage)
            splitter.addWidget(viewer_widget)

        prim_spec_editor_widget = prim_spec_editor.SpecEditorWindow(stage=stage)
        splitter.addWidget(prim_spec_editor_widget)
