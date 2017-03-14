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

        # Create the dialog (after translation) and keep reference
        self.dlg = SegregDialog()

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&Segreg')
        self.toolbar = self.iface.addToolBar(u'Segreg')
        self.toolbar.setObjectName(u'Segreg')

        # Other initializations
        self.layers = []                   # Store layers loaded (non geographical)
        self.lvGroups = QListView()
        self.model = QStandardItemModel(self.dlg.lvGroups)
        self.lvGroups.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.confirmedLayerIndex = 0

        # Segregation measures attributes
        self.attributeMatrix = np.matrix([])    # attributes matrix full size - all columns
        self.location = []                      # x and y coordinates from file (2D lists)
        self.pop = []                           # groups to be analysed [:,3:n] (2D lists)
        self.pop_sum = []                       # sum of population groups from pop (1d array)
        self.locality = []                      # local population intensity for groups
        self.n_location = 0                     # length of list (n lines) (attributeMatrix.shape[0])
        self.n_group = 0                        # number of groups (attributeMatrix.shape[1] - 4)
        self.costMatrix = []                    # scipy cdist distance matrix
        self.track_id = []                      # track ids at string format

        # Local and global internals
        self.local_dissimilarity = []
        self.local_exposure = []
        self.local_entropy = []
        self.local_indexh = []
        self.global_dissimilarity = []
        self.global_exposure = []
        self.global_entropy = []
        self.global_indexh = []

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

        # clear variables at exit
        self.clearVariables()

        # pin view on first tab for attributes selection
        self.dlg.tabWidget.connect(self.dlg.tabWidget, SIGNAL("currentChanged(int)"), self.checkSelectedGroups)

        # initialize dialog loop to add attributes for display
        self.dlg.cbLayers.currentIndexChanged["int"].connect(self.addLayerAttributes)

        # save selected values from user and populate internals
        self.dlg.pbConfirm.clicked.connect(self.confirmButton)

        # run population intensity calculation
        self.dlg.pbRunIntensity.clicked.connect(self.runIntensityButton)

        # run measures from selected check boxes
        self.dlg.pbRunMeasures.clicked.connect(self.runMeasuresButton)

        # select all measures
        self.dlg.pbSelectAll.clicked.connect(self.selectAllMeasures)

        # run dialog to select and save output file
        self.dlg.leOutput.clear()
        self.dlg.pbOpenPath.clicked.connect(self.saveResults)

        # clear variables at exit
        self.dlg.dbClose.clicked.connect(self.clearVariables)

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&Segreg'),
                action)
            self.iface.removeToolBarIcon(action)

        # remove the toolbar
        del self.toolbar

    def clearVariables(self):
        """clear local list and variables"""
        # clear input tables
        self.location = []
        self.pop = []
        self.pop_sum = []
        self.locality = []
        self.n_location = 0
        self.n_group = 0
        self.track_id = []
        self.selectedFields = []

        # clear qt objects
        self.dlg.leOutput.clear()
        self.model.clear()
        self.dlg.leBandwidht.clear()
        for button in self.dlg.gbLocal.findChildren(QCheckBox):
            button.setChecked(False)
        for button in self.dlg.gbGlobal.findChildren(QCheckBox):
            button.setChecked(False)

        # clear results tables
        self.local_dissimilarity = []
        self.local_exposure = []
        self.local_entropy = []
        self.local_indexh = []
        self.global_dissimilarity = []
        self.global_exposure = []
        self.global_entropy = []
        self.global_indexh = []

    def addLayers(self):
        """
        This function add layers from canvas to check box. It only includes non geographic layers.
        This is due to a restriction at scipy funtion CDIST to calculate distance the matrix.
        """
        # clear box
        self.dlg.cbLayers.clear()

        layers_panel = self.iface.legendInterface().layers()
        layer_list = []

        for layer in layers_panel:
            # Check if layer is geographic or projected and append projected only
            isgeographic = layer.crs().geographicFlag()
            if isgeographic is False:
                self.layers.append(layer)
                layer_list.append(layer.name())
            else:
                continue
        # update combo box with layers
        self.dlg.cbLayers.addItems(layer_list)

    def addLayerAttributes(self, layer_index):
        """
        This function populates ID and attributes from layer for selection.
        :param layer_index: index of current selected layer
        """
        # clear list
        self.dlg.cbId.clear()
        self.model.clear()
        selectedLayer = self.layers[layer_index]

        fields = []
        # get attributes from layer
        for i in selectedLayer.pendingFields():
            item = QStandardItem(i.name())
            item.setCheckable(True)
            fields.append(i.name())
            self.model.appendRow(item)

        # Update id and lwGroups combo boxes with fields
        self.dlg.cbId.addItems(fields)
        self.dlg.lvGroups.setModel(self.model)

    def selectGroups(self):
        """Get fileds selected on combo box and return list"""
        selected = []

        # get fileds from model with flag signal
        for i in range(self.model.rowCount()):
            field = self.model.item(i)
            if field.checkState() == 2:
                selected.append(str(field.text()))
        # QMessageBox.critical(None, "Error", str([x for x in selected]))
        return selected

    def checkSelectedGroups(self):
        if self.dlg.tabWidget.currentIndex() == 1:
            if len(self.pop) == 0:
                self.dlg.tabWidget.setTabEnabled(1, False)
                msg = "Please select and confirm the attributes at Input Parameters tab!"
                QMessageBox.critical(None, "Error", msg)

    def confirmButton(self):
        """Confirm selected data and populate local variables"""
        selectedLayerIndex = self.dlg.cbLayers.currentIndex()
        selectedLayer = self.layers[selectedLayerIndex]
        field_names = self.selectGroups()
        self.confirmedLayerIndex = selectedLayerIndex

        # populate track_id data
        id_name = self.dlg.cbId.currentText()
        id_values = selectedLayer.getValues(id_name)[0]
        id_values = [str(x) for x in id_values]
        self.track_id = np.asarray(id_values)
        self.track_id = self.track_id.reshape((len(id_values), 1))

        # return x and y from polygons centroids
        x_cord = [feat.geometry().centroid().asPoint().x() for feat in selectedLayer.getFeatures()]
        x_cord = np.reshape(x_cord, (len(x_cord), 1))
        y_cord = [feat.geometry().centroid().asPoint().y() for feat in selectedLayer.getFeatures()]
        y_cord = np.reshape(y_cord, (len(y_cord), 1))

        # populate groups data based on selected list
        groups = []
        for i in field_names:
            values = selectedLayer.getDoubleValues(i)[0]  # getDoubleValues for float
            group = [float(x) for x in values]
            groups.append(group)
        groups = np.asarray(groups).T

        if len(groups) == 0:
            QMessageBox.critical(None, "Error", 'No data selected!')
            self.dlg.tabWidget.setTabEnabled(1, False)
            return

        # concatenate values and populate attribute matrix
        data = np.concatenate((x_cord, y_cord, groups), axis=1)
        self.attributeMatrix = np.asmatrix(data)
        n = self.attributeMatrix.shape[1]
        self.location = self.attributeMatrix[:, 0:2]
        self.location = self.location.astype('float')
        self.pop = self.attributeMatrix[:, 2:n]
        self.pop[np.where(self.pop < 0)[0], np.where(self.pop < 0)[1]] = 0.0
        self.n_group = n - 2
        self.n_location = self.attributeMatrix.shape[0]
        self.pop_sum = np.sum(self.pop, axis=1)

        # unlock measures tab and display confirmation if success
        if self.attributeMatrix is not None:
            self.dlg.tabWidget.setTabEnabled(1, True)
            self.iface.messageBar().pushMessage("Info", "Input saved", level=QgsMessageBar.INFO, duration=2)

    def runIntensityButton(self):
        if not np.any(self.pop):
            QMessageBox.critical(None, "Error", 'No group selected!')
        else:
            # set fixed IDs for radioButtons
            self.dlg.bgWeight.setId(self.dlg.gauss, 1)
            self.dlg.bgWeight.setId(self.dlg.bisquar, 2)
            self.dlg.bgWeight.setId(self.dlg.mvwind, 3)

            # set parameters to call locality matrix
            weight = self.dlg.bgWeight.checkedId()
            bw = int(self.dlg.leBandwidht.text())

            self.cal_localityMatrix(bw, weight)
            self.iface.messageBar().pushMessage("Info", "Matrix of shape %s computed" % str(self.locality.shape),
                                                level=QgsMessageBar.INFO, duration=4)

    def getWeight(self, distance, bandwidth, weightmethod=1):
        """
        This function computes the weights for neighborhood. Default value is Gaussian(1)
        :param distance: distance in meters to be considered for weighting
        :param bandwidth: bandwidth in meters selected to perform neighborhood
        :param weightmethod: method to be used: 1-gussian , 2-bi square and 3-moving window
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
        elif weightmethod == 3:
            weight = (1 + (distance * 0))
            sel = np.where(distance > bandwidth)
            weight[sel[0]] = 0
        else:
            raise Exception('Invalid weight method selected!')
        return weight

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

    def cal_localDissimilarity(self):
        """
        Compute local dissimilarity for all groups.
        :return: 1d array like with results for all groups, size of localities
        """
        if len(self.locality) == 0:
            lj = np.ravel(self.pop_sum)
            tjm = np.asarray(self.pop) * 1.0 / lj[:, None]
            tm = np.sum(self.pop, axis=0) * 1.0 / np.sum(self.pop)
            index_i = np.sum(np.asarray(tm) * np.asarray(1 - tm))
            pop_total = np.sum(self.pop)
            local_diss = np.sum(1.0 * np.array(np.fabs(tjm - tm)) *
                                np.asarray(self.pop_sum).ravel()[:, None] / (2 * pop_total * index_i), axis=1)
        else:
            lj = np.asarray(np.sum(self.locality, axis=1))
            tjm = self.locality * 1.0 / lj[:, None]
            tm = np.sum(self.pop, axis=0) * 1.0 / np.sum(self.pop)
            index_i = np.sum(np.asarray(tm) * np.asarray(1 - tm))
            pop_total = np.sum(self.pop)
            local_diss = np.sum(1.0 * np.array(np.fabs(tjm - tm)) *
                                np.asarray(self.pop_sum).ravel()[:, None] / (2 * pop_total * index_i), axis=1)
        local_diss = np.nan_to_num(local_diss)
        local_diss = np.asmatrix(local_diss).transpose()
        self.local_dissimilarity = local_diss

    def cal_globalDissimilarity(self):
        """
        This function call local dissimilarity and compute the sum from individual values.
        :return: display global value
        """
        local_diss = self.local_dissimilarity
        self.global_dissimilarity = np.sum(local_diss)

    def cal_localExposure(self):
        """
        This function computes the local exposure index of group m to group n.
        in situations where m=n, then the result is the isolation index.
        :return: 2d list with individual indexes
        """
        m = self.n_group
        j = self.n_location
        exposure_rs = np.zeros((j, (m * m)))
        if len(self.locality) == 0:
            local_expo = np.asarray(self.pop) * 1.0 / np.asarray(np.sum(self.pop, axis=0)).ravel()
            locality_rate = np.asarray(self.pop) * 1.0 / np.asarray(np.sum(self.pop, axis=1)).ravel()[:, None]
            for i in range(m):
                exposure_rs[:, ((i * m) + 0):((i * m) + m)] = np.asarray(locality_rate) * \
                                                              np.asarray(local_expo[:, i]).ravel()[:, None]
        else:
            local_expo = np.asarray(self.pop) * 1.0 / np.asarray(np.sum(self.pop, axis=0)).ravel()
            locality_rate = np.asarray(self.locality) * 1.0 / np.asarray(np.sum(self.locality, axis=1)).ravel()[:, None]
            for i in range(m):
                exposure_rs[:, ((i * m) + 0):((i * m) + m)] = np.asarray(locality_rate) * \
                                                              np.asarray(local_expo[:, i]).ravel()[:, None]
        exposure_rs[np.isinf(exposure_rs)] = 0
        exposure_rs[np.isnan(exposure_rs)] = 0
        exposure_rs = np.asmatrix(exposure_rs)
        self.local_exposure = exposure_rs

    def cal_globalExposure(self):
        """
        This function call local exposure function and sum the results for the global index.
        :return: displays global number result
        """
        m = self.n_group
        local_exp = self.local_exposure
        global_exp = np.sum(local_exp, axis=0)
        global_exp = global_exp.reshape((m, m))
        self.global_exposure = global_exp

    def cal_localEntropy(self):
        """
        This function computes the local entropy score for a unit area Ei (diversity). A unit within the
        metropolitan area, such as a census tract. If population intensity was previously computed,
        the spatial version will be returned, else the non spatial version will be selected (raw data).
        :return: 2d array with local indices
        """
        if len(self.locality) == 0:
            proportion = np.asarray(self.pop / self.pop_sum)
        else:
            proportion = np.asarray(self.locality / np.sum(self.locality))
        entropy = proportion * np.log(1 / proportion)
        entropy[np.isnan(entropy)] = 0
        entropy[np.isinf(entropy)] = 0
        entropy = np.sum(entropy, axis=1)
        entropy = entropy.reshape((self.n_location, 1))
        self.local_entropy = entropy

    def cal_globalEntropy(self):
        """
        This function computes the global entropy score E (diversity). A metropolitan area's entropy score.
        :return: diversity score
        """
        group_score = []
        if len(self.locality) == 0:
            pop_total = np.sum(self.pop_sum)
            prop = np.asarray(np.sum(self.pop, axis=0))[0]
        else:
            pop_total = np.sum(self.locality)
            prop = np.asarray(np.sum(self.locality, axis=0))
        for group in prop:
            group_idx = group / pop_total * np.log(1 / (group / pop_total))
            group_score.append(group_idx)
        global_entro = np.sum(group_score)
        self.global_entropy = global_entro

    def cal_localIndexH(self):
        """
        This function computes the local entropy index H for all localities. The functions cal_localEntropy() for
        local diversity and cal_globalEntropy for global entropy are called as input. If population intensity
        was previously computed, the spatial version will be returned, else the non spatial version will be
        selected (raw data).
        :return: array like with scores for n groups (size groups)
        """
        local_entropy = self.local_entropy
        global_entropy = self.global_entropy
        if len(self.locality) == 0:
            et = np.asarray(global_entropy * np.sum(self.pop_sum))
            eei = np.asarray(global_entropy - local_entropy)
            h_local = eei * np.asarray(self.pop_sum) / et
        else:
            et = np.asarray(global_entropy * np.sum(self.locality))
            eei = np.asarray(global_entropy - local_entropy)
            h_local = eei * np.sum(self.locality) / et
        self.local_indexh = h_local

    def cal_globalIndexH(self):
        """
        Function to compute global index H returning the sum of local values. The function cal_localIndexH is
        called as input for sum of individual values.
        :return: values with global index for each group.
        """
        h_local = self.local_indexh
        h_global = np.sum(h_local, axis=0)
        self.global_indexh = h_global

    def selectAllMeasures(self):
        """Select all check box on measures groups"""
        for button in self.dlg.gbLocal.findChildren(QCheckBox):
            button.setChecked(True)
        for button in self.dlg.gbGlobal.findChildren(QCheckBox):
            button.setChecked(True)

    def runMeasuresButton(self):
        """
        This function call the functions to compute local and global measures. It populates internals
        with lists holding the results for saving.
        """
        # call local and global exposure/isolation measures
        if self.dlg.expo_global.isChecked() is True:
            self.cal_localExposure()
            self.cal_globalExposure()
        if self.dlg.expo_local.isChecked() is True and len(self.local_exposure) == 0:
            self.cal_localExposure()

        # call local and global dissimilarity measures
        if self.dlg.diss_global.isChecked() is True:
            self.cal_localDissimilarity()
            self.cal_globalDissimilarity()
        if self.dlg.diss_local.isChecked() is True and len(self.local_dissimilarity) == 0:
            self.cal_localDissimilarity()

        # call local and global entropy measures
        if self.dlg.entro_global.isChecked() is True:
            self.cal_localEntropy()
            self.cal_globalEntropy()
        if self.dlg.entro_local.isChecked() is True and len(self.local_entropy) == 0:
            self.cal_localEntropy()

        # call local and global index H measures
        if self.dlg.idxh_global.isChecked() is True:
            self.cal_localEntropy()
            self.cal_globalEntropy()
            self.cal_localIndexH()
            self.cal_globalIndexH()
        if self.dlg.idxh_local.isChecked() is True and len(self.local_indexh) == 0:
            self.cal_localEntropy()
            self.cal_globalEntropy()
            self.cal_localIndexH()

        QMessageBox.information(None, "Info", 'Measures computed successfully!')

    def joinResultsData(self):
        """ Function to join results on a unique matrix and assign names for columns"""
        names = ['id','x','y']
        for i in range(self.n_group):
            names.append('group_' + str(i))

        measures_computed = []
        if len(self.locality) != 0:
            measures_computed.append('self.locality')
            for i in range(self.n_group):
                names.append('intens_' + str(i))

        if self.dlg.expo_local.isChecked() is True:
            measures_computed.append('self.local_exposure')
            for i in range(self.n_group):
                for j in range(self.n_group):
                    if i == j:
                        names.append('iso_' + str(i) + str(j))
                    else:
                        names.append('exp_' + str(i) + str(j))

        if self.dlg.diss_local.isChecked() is True:
            measures_computed.append('self.local_dissimilarity')
            names.append('dissimil')

        if self.dlg.entro_local.isChecked() is True:
            measures_computed.append('self.local_entropy')
            names.append('entropy')

        if self.dlg.idxh_local.isChecked() is True:
            measures_computed.append('self.local_indexh')
            names.append('indexh')

        output_labels = tuple([eval(x) for x in measures_computed])
        try:
            computed_results = np.concatenate(output_labels, axis=1)
            results_matrix = np.concatenate((self.track_id, self.attributeMatrix, computed_results), axis=1)
            measures_computed[:] = []
            return results_matrix, names
        except ValueError:
            results_matrix = np.concatenate((self.track_id, self.attributeMatrix), axis=1)
            return results_matrix, names
        except:
            QMessageBox.critical(None, "Error", 'Could not join result data!')
            raise

    def addShapeToCanvas(self, result, path):
        """Function to add results to Canvas as a shape file"""
        # get data from layer confirmed on groups selection
        sourceLayer = self.layers[self.confirmedLayerIndex]
        sourceFeats = [feat for feat in sourceLayer.getFeatures()]
        sourceGeometryType = ['Point','Line','Polygon'][sourceLayer.geometryType()]
        sourceCRS = sourceLayer.crs().authid()

        # data for new layer
        name = QFileInfo(path).baseName()
        data = result[0][:, (3 + self.n_group):]
        labels = result[1][(3 + self.n_group):]

        # create layer copying data from sourceLayer
        newLayer = QgsVectorLayer(sourceGeometryType + '?crs='+sourceCRS, name, "memory")
        provider = newLayer.dataProvider()
        attr = sourceLayer.dataProvider().fields().toList()
        attr.extend([QgsField(label, QVariant.Double) for label in labels])
        provider.addFeatures(sourceFeats)
        provider.addAttributes(attr)
        newLayer.updateFields()

        # add results from measures selected for calculation
        for idxfeat, feat in enumerate(newLayer.getFeatures()):
            featid = int(feat.id())
            for idxlabel, label in enumerate(labels):
                idxfield = int(provider.fieldNameMap()[label])
                val = float(data[idxfeat, idxlabel])
                provider.changeAttributeValues({featid : {idxfield : val}})

        # add new layer to canvas        
        QgsMapLayerRegistry.instance().addMapLayer(newLayer)

        # QMessageBox.critical(None, "Info", str([f.name() for f in newLayer.pendingFields()]))
        # QMessageBox.critical(None, "Info", str(attr))

        # for idxfeat, feat in enumerate(newLayer.getFeatures()):
        #     featid = int(feat.id())
        #     for idxlabel, label in enumerate(labels):
        #         # idxfield = provider.fieldNameMap()[label]
        #         val = float(data[idxfeat, idxlabel])
        #         newLayer.startEditing()
        #         feat[label] = val
        #         newLayer.updateFeature(feat)
        #         # newLayer.changeAttributeValue(featid, idxfield, val)
        #         newLayer.commitChanges()

        # # add results from measures selected for calculation
        # for idxfeat, feat in enumerate(newLayer.getFeatures()):
        #     for idxlabel, label in enumerate(labels):
        #         provider.changeAttributeValues({feat.id() : {provider.fieldNameMap()[label] : data[idxfeat, idxlabel]}})

        # for idxlabel, label in enumerate(labels):
            # dataSlice = data[:,idxlabel]
            # for idxfeat, feat in enumerate(newLayer.getFeatures()):
            #     provider.changeAttributeValues({feat.id() : {provider.fieldNameMap()[label] : dataSlice[idxfeat]}})

        # QgsVectorFileWriter(path, u'UTF-8', newLayer.fields(), QGis.WKBPolygon, newLayer.csr())

        # add layer to canvas
        # QgsMapLayerRegistry.instance().addMapLayer(newLayer)
        # QMessageBox.critical(None, "Info", str(QgsMapLayerRegistry.instance().count()))


    def saveResults(self):
        """ Function to save results to a local file."""
        filename = QFileDialog.getSaveFileName(self.dlg, "Select output file ", "", "*.csv")
        self.dlg.leOutput.setText(filename)
        path = self.dlg.leOutput.text()
        result = self.joinResultsData()
        labels = str(', '.join(result[1]))

        # fmts = ["%g" for i in result[1].split()]
        # fmts[0] = "%s"
        # fmts = str(', '.join(fmts))
        # QMessageBox.critical(None, "Error", str(result[0][1,1]))
        # fi = str(QFileInfo(path).baseName())
        # QMessageBox.critical(None, "Error", str(fi))

        np.savetxt(path, result[0], header=labels, delimiter=',', newline='\n', fmt="%s")

        # add result to canvas as shape file if requested
        if self.dlg.addToCanvas.isChecked() is True:
            self.addShapeToCanvas(result, path)

        # save global results to a second local file
        with open("%s_global.csv" % path, "w") as f:
            f.write('Global dissimilarity: ' + str(self.global_dissimilarity))
            f.write('\nGlobal entropy: ' + str(self.global_entropy))
            f.write('\nGlobal Index H: ' + str(self.global_indexh))
            f.write('\nGlobal isolation/exposure: \n')
            f.write(str(self.global_exposure))

        # clear local variables after save
        self.local_dissimilarity = []
        self.local_exposure = []
        self.local_entropy = []
        self.local_indexh = []

    def run(self):
        """Run method to call dialog and connect interface with functions"""

        # pin view on first tab for attributes selection
        self.dlg.tabWidget.setCurrentIndex(0)

        # # clear variables at exit
        self.clearVariables()

        # populate layers list using a projected CRS
        self.addLayers()

        # show the dialog
        self.dlg.show()

        if not self.layers:
            QMessageBox.critical(None, "Error", 'No layer found!')
            return

        # Run the dialog event loop
        result = self.dlg.exec_()

        # See if OK was pressed
        if result:
            # exit
            pass

# TODO Interface losing setup between systems
# TODO implement function to add shapefile to canvas
# TODO Bug with H index
