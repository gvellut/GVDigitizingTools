# -*- coding: utf-8 -*-

# Import the PyQt and QGIS libraries
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
from qgis.gui import *


class MessageBarUtils(object):
    
    def __init__(self, iface):
        self.iface = iface
        self.widgets = []
    
    def showYesCancel(self, title, text, level = QgsMessageBar.INFO, yesCallback = None, cancelCallback = None, hideAfterButton = True, clearMessages = True):
        if clearMessages:
            self.removeAllMessages()
            
        widget = QgsMessageBar.createMessage(title, text)
        button = QPushButton(widget)
        button.setText("Yes")
        button.pressed.connect(self.wrap(widget, yesCallback, hideAfterButton))
        widget.layout().addWidget(button)
        button = QPushButton(widget)
        button.setText("Cancel")
        button.pressed.connect(self.wrap(widget, cancelCallback, hideAfterButton))
        widget.layout().addWidget(button)  
        self.iface.messageBar().pushWidget(widget, level)
        
        self.widgets.append(widget)
        
    def showButton(self, title, text, buttonText, level = QgsMessageBar.INFO, buttonCallback = None, hideAfterButton = True, clearMessages = True):
        if clearMessages:
            self.removeAllMessages()
            
        widget = QgsMessageBar.createMessage(title, text)
        button = QPushButton(widget)
        button.setText(buttonText)
        button.pressed.connect(self.wrap(widget, buttonCallback, hideAfterButton))
        widget.layout().addWidget(button)
        self.iface.messageBar().pushWidget(widget, level)
        
        self.widgets.append(widget)
        
    def wrap(self, widget, callback, hideAfterButton):
        """
        Wrapper to handle hiding and callbacks
        """
        def wrapped():
            if hideAfterButton:
                self.iface.messageBar().popWidget(widget)
            if callback:
                callback()
                
        return wrapped
        
    def showMessage(self, title, text, level = QgsMessageBar.INFO, duration = 5, clearMessages = True):
        if clearMessages:
            self.removeAllMessages()
            
        widget = QgsMessageBar.createMessage(title, text)
        self.iface.messageBar().pushWidget(widget, level, duration)
        
        if duration == 0:
            self.widgets.append(widget)
         
    def showProgress(self, title,text, level = QgsMessageBar.INFO, clearMessages = True):
        if clearMessages:
            self.removeAllMessages()
            
        widget = QgsMessageBar.createMessage(title, text)
        progress = QProgressBar()
        progress.setAlignment(Qt.AlignLeft)
        progress.setValue(0)
        progress.setMaximum(100)           
        widget.layout().addWidget(progress)
        self.iface.messageBar().pushWidget(widget, level)
        
        self.widgets.append(widget)
        
        return (widget, progress)
    
    def showCombobox(self, title, text, comboboxItems, defaultIndex=None, level = QgsMessageBar.INFO, changeValueCallback = None, clearMessages = True):
        if clearMessages:
            self.removeAllMessages()
            
        widget = QgsMessageBar.createMessage(title, text)
        comboBox = QComboBox()
        comboBox.addItems(comboboxItems)
        if defaultIndex <> None:
            comboBox.setCurrentIndex(defaultIndex)
        
        if changeValueCallback:
            comboBox.currentIndexChanges.connect(changeValueCallback)
            
        widget.layout().addWidget(comboBox)
        self.iface.messageBar().pushWidget(widget, level)
        
        self.widgets.append(widget)
        
        return widget, comboBox
    
    def showLineEdit(self, title,text, defaultValue, level = QgsMessageBar.INFO, clearMessages = True):
        if clearMessages:
            self.removeAllMessages()
            
        widget = QgsMessageBar.createMessage(title, text)
        lineEdit = QLineEdit()
        lineEdit.setAlignment(Qt.AlignLeft)
        lineEdit.setText(str(defaultValue))        
        widget.layout().addWidget(lineEdit)
        self.iface.messageBar().pushWidget(widget, level)
        
        self.widgets.append(widget)
        
        return (widget, lineEdit)
        
    
    def removeAllMessages(self):
        for widget in self.widgets:
            try: self.iface.messageBar().popWidget(widget)
            except:pass
        self.widgets = []
