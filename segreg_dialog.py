# -*- coding: utf-8 -*-
"""
/***************************************************************************
 SegregDialog
                                 A QGIS plugin
 This plugin computes spatial and non spatial segregation measures
                             -------------------
        begin                : 2017-01-25
        git sha              : $Format:%H$
        copyright            : (C) 2017 by Sandro Sousa / USP-UFABC
        email                : sandrofsousa@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

import os

from PyQt4 import QtGui, uic

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'segreg_dialog_base.ui'))


class SegregDialog(QtGui.QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        """Constructor."""
        super(SegregDialog, self).__init__(parent)
        # Set up the user interface from Designer.
        self.setupUi(self)
