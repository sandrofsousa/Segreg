# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Segreg
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
from qgis.core import *
from PyQt4.QtGui import *
from PyQt4.QtCore import *
from qgis.utils import *
import numpy as np
from scipy.spatial.distance import cdist

# Initialize Qt resources from file resources.py
import resources
# Import the code for the dialog
from segreg_dialog import SegregDialog
import os.path


class Segreg:
    def __init__(self, iface):
        """Constructor.
        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'Segreg_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)

            if qVersion() > '4.3.3':
                QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&Segreg')
        self.toolbar = self.iface.addToolBar(u'Segreg')
        self.toolbar.setObjectName(u'Segreg')

        # Other initializations
        self.layers = []                        # Store layers loaded (non geographical)
        self.lwGroups = QListView()
        self.model = QStandardItemModel(self.lwGroups)
        self.lwGroups.setAcceptDrops(True)
        #self.lwGroups = QListWidget()
        #self.lwGroups.setSelectionMode(QAbstractItemView.ExtendedSelection)

        # Connect buttons to functions
        # self.dlg.pushButton_1.clicked.connect(self.confirmButton)

        # Segregation measures attributes
        self.attributeMatrix = np.matrix([])    # attributes matrix full size - all columns
        self.location = []                      # x and y coordinates from file (2D lists)
        self.pop = []                           # groups to be analysed [:,4:n] (2D lists)
        self.pop_sum = []                       # sum of population groups from pop (1d array)
        self.locality = []                      # local population intensity for groups
        self.n_location = 0                     # length of list (n lines) (attributeMatrix.shape[0])
        self.n_group = 0                        # number of groups (attributeMatrix.shape[1] - 4)
        self.costMatrix = []                    # scipy cdist distance matrix
        self.track_id = []                      # track ids at string format

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('Segreg', message)

    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Add a toolbar icon to the toolbar.
        """

        # Create the dialog (after translation) and keep reference
        self.dlg = SegregDialog()

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/Segreg/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Compute segregation measures'),
            callback=self.run,
            parent=self.iface.mainWindow())

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&Segreg'),
                action)
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar

    def addLayers(self):
        # clear box
        self.dlg.cbLayers.clear()

        self.layers = self.iface.legendInterface().layers()
        layer_list = []
        for layer in self.layers:
            # Check if layer is geographic or projected and append projected only
            isgeographic = layer.crs().geographicFlag()
            if isgeographic is False:
                layer_list.append(layer.name())
            else:
                continue
        # update combo box with layers
        self.dlg.cbLayers.addItems(layer_list)

    def addLayerAttributes(self, layer_index):
        # clear list
        self.dlg.cbId.clear()
        self.dlg.lwGroups.clear()
        selectedLayer = self.layers[layer_index]
        
        fields = []
        # get attributes from layer
        for i in selectedLayer.pendingFields():
            fields.append(i.name())
        # Update id and lwGroups combo boxes with fields
        self.dlg.cbId.addItems(fields)
        self.dlg.lwGroups.addItems(fields)

    def selectId(self, layer_index):
        # clear box
        self.dlg.cbId.clear()
        selectedLayer = self.layers[layer_index]
        fields = []
        
        # get attributes from layer
        for field in selectedLayer.pendingFields():
            fields.append(field.name())
        # Update id on combo box with fields
        self.dlg.cbId.addItems(fields)

    def selectGroups(self, layer_index):
        self.dlg.lwGroups.clear()
        selectedLayer = self.layers[layer_index]
        fields = []
    
        # get attributes from layer
        for i in selectedLayer.pendingFields():
            field = QListWidgetItem()
            field.setText(i.name())
            self.dlg.lwGroups.addItem(field)
        #self.dlg.lwGroups.currentRow.setItemSelected(True)

    def confirmButton(self):
        selectedLayerIndex = self.dlg.cbLayers.currentIndex()
        selectedLayer = self.layers[selectedLayerIndex]
        field_names = [str(field.name()) for field in selectedLayer.pendingFields()][1:]

        # populate track_id data
        id_name = self.dlg.cbId.currentText()
        id_values = selectedLayer.getValues(id_name)[0]  #getDoubleValues for float
        id_values = [str(x) for x in id_values]
        self.track_id = np.asarray(id_values)
        self.track_id = self.track_id.reshape((len(id_values), 1))

        # return x and y from polygons centroids
        x_cord = [feat.geometry().centroid().asPoint().x() for feat in selectedLayer.getFeatures()]
        x_cord = np.reshape(x_cord, (len(x_cord), 1))
        y_cord = [feat.geometry().centroid().asPoint().y() for feat in selectedLayer.getFeatures()]
        y_cord = np.reshape(y_cord, (len(y_cord), 1))

        # populate groups data
        groups = []
        for i in field_names:
            values = selectedLayer.getDoubleValues(i)[0]  #getDoubleValues for float
            group = [int(x) for x in values]
            groups.append(group)
        groups = np.asarray(groups).T

        # concatenate values and populate attribute matrix
        data = np.concatenate((x_cord, y_cord, groups), axis=1)
        self.attributeMatrix = np.asmatrix(data)
        n = self.attributeMatrix.shape[1]
        self.location = self.attributeMatrix[:, 0:2]
        self.location = self.location.astype('float')
        self.pop = self.attributeMatrix[:, 2:n]
        self.pop[np.where(self.pop < 0)[0], np.where(self.pop < 0)[1]] = 0
        self.n_group = n - 2
        self.n_location = self.attributeMatrix.shape[0]
        self.pop_sum = np.sum(self.pop, axis=1)

        self.iface.messageBar().pushMessage("Info", "Selection saved", level=QgsMessageBar.INFO, duration=3)


    # def selectedWeight(self):
    #     self.dlg.gauss.clicked.connect()
    #     self.dlg.bisquar.clicked.connect()
    #     self.dlg.mvwind.clicked.connect()


    def runIntensityButton(self):
        self.dlg.bgWeight.setId(self.dlg.gauss, 1)
        self.dlg.bgWeight.setId(self.dlg.bisquar, 2)
        self.dlg.bgWeight.setId(self.dlg.mvwind, 3)

        weight = self.dlg.bgWeight.checkedId()
        bw = int(self.dlg.leBandwidht.text())

        self.cal_localityMatrix(bw, weight)
        self.iface.messageBar().pushMessage("Info", str(len(self.locality)), level=QgsMessageBar.INFO, duration=2)

    def cal_localityMatrix(self, bandwidth=5000, weightmethod=1):
        """
        This function calculate the local population intensity for all groups.
        :param bandwidth: bandwidth for neighborhood in meters
        :param weightmethod: 1 for gaussian, 2 for bi-square and empty for moving window
        :return: 2d array like with population intensity for all groups
        """
        n_local = self.location.shape[0]
        n_subgroup = self.pop.shape[1]
        locality_temp = np.empty([n_local, n_subgroup])
        for index in range(0, n_local):
            for index_sub in range(0, n_subgroup):
                cost = cdist(self.location[index, :], self.location)
                weight = self.getWeight(cost, bandwidth, weightmethod)
                locality_temp[index, index_sub] = np.sum(weight * np.asarray(self.pop[:, index_sub]))/np.sum(weight)
        self.locality = locality_temp
        self.locality[np.where(self.locality < 0)[0], np.where(self.locality < 0)[1]] = 0

        fname = "C:/Users/sandro/groups.txt"
        np.savetxt(fname, self.locality, delimiter=',', newline='\n')

    def getWeight(self, distance, bandwidth, weightmethod=1):
        """
        This function computes the weights for neighborhood. Default value is Gaussian(1)
        :param distance: distance in meters to be considered for weighting
        :param bandwidth: bandwidth in meters selected to perform neighborhood
        :param weightmethod: method to be used: 1-gussian , 2-bi square and empty-moving windows
        :return: weight value for internal use
        """
        distance = np.asarray(distance.T)
        if weightmethod == 1:
            weight = np.exp((-0.5) * (distance / bandwidth) * (distance / bandwidth))
        elif weightmethod == 2:
            weight = (1 - (distance / bandwidth) * (distance / bandwidth)) * (
            1 - (distance / bandwidth) * (distance / bandwidth))
            sel = np.where(distance > bandwidth)
            weight[sel[0]] = 0
        else:
            weight = 1
            sel = np.where(distance > bandwidth)
            weight[sel[0], :] = 0
        return weight

    def clicked(self, item):
        #self.dlg.lwGroups.item.setBackgroundColor("blue")
        QMessageBox.information(self, "lwGroups", "You clicked: "+item.text())


    def run(self):
        """Run method that performs all the real work"""
        # show the dialog
        self.dlg.show()

        # populate layers list with a projected CRS
        self.addLayers()

        # populate initial view with first layer
        selectedLayerIndex = self.dlg.cbLayers.currentIndex()
        self.addLayerAttributes(selectedLayerIndex)

        # initialize dialog loop to add attributes for display
        self.dlg.cbLayers.currentIndexChanged["int"].connect(self.addLayerAttributes)

        # save selected values from user and populate internals
        self.dlg.pbConfirm.clicked.connect(self.confirmButton)

        # run population intensity calculation
        self.dlg.pbRunIntensity.clicked.connect(self.runIntensityButton)

        # # position on current layer selected from list view
        # if self.layers is None:
        #self.iface.messageBar().pushMessage("Info", "%s" % var, level=QgsMessageBar.INFO, duration=3)
        
        #self.dlg.cbLayers.currentIndexChanged["int"].connect(self.selectId)
        #self.dlg.cbLayers.currentIndexChanged["int"].connect(self.selectGroups)
        
        #self.dlg.connect(self.lwGroups, SIGNAL("itemSelectionChanged()"), self.clicked)

        # Run the dialog event loop
        self.dlg.exec_()