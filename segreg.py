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
        self.lvGroups = QListView()
        self.model = QStandardItemModel(self.dlg.lvGroups)
        self.lvGroups.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.confirmedLayerName = None
        self.dlg.plainTextEdit.setReadOnly(True)

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

        # clear variables at start
        self.clearVariables()

        # check if attributes were selected if change tab
        self.dlg.tabWidget.currentChanged.connect(self.checkSelectedGroups)

        # initialize dialog loop to add attributes for display
        self.dlg.cbLayers.currentIndexChanged.connect(self.addLayerAttributes)

        # connect to button to save selected values from user and populate internals
        self.dlg.pbConfirm.clicked.connect(self.confirmButton)

        # connect to button to run population intensity calculation
        self.dlg.pbRunIntensity.clicked.connect(self.runIntensityButton)

        # connect to button to run measures from selected check boxes
        self.dlg.pbRunMeasures.clicked.connect(self.runMeasuresButton)

        # connect to button to select all measures
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
        """clear local lists and variables"""
        # clear input tables
        self.location = []
        self.pop = []
        self.pop_sum = []
        self.locality = []
        self.n_location = 0
        self.n_group = 0
        self.track_id = []
        self.selectedFields = []
        self.layers = []

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
        Add layers from canvas to combo box. It only includes non geographic layers.
        This is due to a restriction at scipy funtion CDIST to compute distance matrix.
        """
        # clear combo box
        self.dlg.cbLayers.clear()

        layer_list = []
        for layer in QgsMapLayerRegistry.instance().mapLayers().values():
            # Check if layer is geographic or projected and append projected only
            isgeographic = layer.crs().geographicFlag()
            if isgeographic is False:
                layer_list.append(layer.name())
            else:
                continue
        # update combo box with layers
        self.dlg.cbLayers.addItems(layer_list)

    def addLayerAttributes(self):
        """
        Populates ID and attributes from layer for user selection. Position on
        current layer name from combo box.
        """
        # clear qt objects
        self.dlg.cbId.clear()
        self.model.clear()
        layerName = self.dlg.cbLayers.currentText()

        try:
            selectedLayer = QgsMapLayerRegistry.instance().mapLayersByName(layerName)[0]
            fields = []
            # get attributes from layer
            for i in selectedLayer.pendingFields():
                item = QStandardItem(i.name())
                item.setCheckable(True)
                fields.append(i.name())
                self.model.appendRow(item)

            # Update id and groups combo boxes with values
            self.dlg.cbId.addItems(fields)
            self.dlg.lvGroups.setModel(self.model)
        except:
            return

    def selectGroups(self):
        """Get fields selected on combo box and return list"""
        selected = []
        # get fields from model with flag signal
        for i in range(self.model.rowCount()):
            field = self.model.item(i)
            if field.checkState() == 2:
                selected.append(str(field.text()))
        return selected

    def checkSelectedGroups(self):
        """Check if groups were selected and confirmed before moving to measures tab"""
        if self.dlg.tabWidget.currentIndex() == 1:
            if len(self.pop) == 0:
                self.dlg.tabWidget.setTabEnabled(1, False)
                msg = "Please select and confirm the attributes at Input Parameters tab!"
                QMessageBox.critical(None, "Error", msg)

    def confirmButton(self):
        """Populate local variables (attributes matrix) with selected fields"""
        # get layer and fields from combo box items
        layerName = self.dlg.cbLayers.currentText()
        selectedLayer = QgsMapLayerRegistry.instance().mapLayersByName(layerName)[0]
        field_names = self.selectGroups()
        # to be used later to save results as shapefile
        self.confirmedLayerName = layerName

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

        # populate groups data based on selected fields list
        groups = []
        for i in field_names:
            values = selectedLayer.getDoubleValues(i)[0]  # getDoubleValues for float
            group = [float(x) for x in values]
            groups.append(group)
        groups = np.asarray(groups).T

        # check if fields were selected
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
            self.iface.messageBar().pushMessage("Info",
             "Input saved", level=QgsMessageBar.INFO, duration=2)

    def runIntensityButton(self):
        """Run population intensity for selected bandwidth and weight method"""
        if not np.any(self.pop):
            QMessageBox.critical(None, "Error", 'No group selected!')
        else:
            # set fixed IDs for radioButtons according to weightmethod
            self.dlg.bgWeight.setId(self.dlg.gauss, 1)
            self.dlg.bgWeight.setId(self.dlg.bisquar, 2)
            self.dlg.bgWeight.setId(self.dlg.mvwind, 3)

            # set parameters to call locality matrix
            weight = self.dlg.bgWeight.checkedId()
            bw = int(self.dlg.leBandwidht.text())

            # check if weight method was selected
            if weight == -1:
                QMessageBox.critical(None, "Error", "Please select a weight method")
            else:
                self.cal_localityMatrix(bw, weight)
                self.iface.messageBar().pushMessage("Info",
                 "Matrix of shape %s computed" % str(self.locality.shape),
                                                level=QgsMessageBar.INFO,
                                                duration=4)

    def getWeight(self, distance, bandwidth, weightmethod=1):
        """
        Compute the weights for neighborhood.
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

    def cal_localityMatrix(self, bandwidth, weightmethod):
        """
        Compute the local population intensity for all groups.
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
        # assign zero to negative values
        self.locality[np.where(self.locality < 0)[0], np.where(self.locality < 0)[1]] = 0

    def cal_localDissimilarity(self):
        """
        Compute local dissimilarity for all groups.
        """
        # non-spatial version loop, uses raw data
        if len(self.locality) == 0:
            lj = np.ravel(self.pop_sum)
            tjm = np.asarray(self.pop) * 1.0 / lj[:, None]
            tm = np.sum(self.pop, axis=0) * 1.0 / np.sum(self.pop)
            index_i = np.sum(np.asarray(tm) * np.asarray(1 - tm))
            pop_total = np.sum(self.pop)
            local_diss = np.sum(1.0 * np.array(np.fabs(tjm - tm)) *
                                np.asarray(self.pop_sum).ravel()[:, None] / (2 * pop_total * index_i), axis=1)
        # spatial version loop, uses population intensity
        else:
            lj = np.asarray(np.sum(self.locality, axis=1))
            tjm = self.locality * 1.0 / lj[:, None]
            tm = np.sum(self.pop, axis=0) * 1.0 / np.sum(self.pop)
            index_i = np.sum(np.asarray(tm) * np.asarray(1 - tm))
            pop_total = np.sum(self.pop)
            local_diss = np.sum(1.0 * np.array(np.fabs(tjm - tm)) *
                                np.asarray(self.pop_sum).ravel()[:, None] / (2 * pop_total * index_i), axis=1)

        # clear nan values and transpose matrix
        local_diss = np.nan_to_num(local_diss)
        local_diss = np.asmatrix(local_diss).transpose()
        self.local_dissimilarity = local_diss

    def cal_globalDissimilarity(self):
        """
        Compute global dissimilarity calling the local version and summing up.
        """
        local_diss = self.local_dissimilarity
        self.global_dissimilarity = np.sum(local_diss)

    def cal_localExposure(self):
        """
        Compute the local exposure index of group m to group n.
        in situations where m=n, then the result is the isolation index.
        """
        m = self.n_group
        j = self.n_location
        exposure_rs = np.zeros((j, (m * m)))
        # non-spatial version loop, uses raw data
        if len(self.locality) == 0:
            local_expo = np.asarray(self.pop) * 1.0 / np.asarray(np.sum(self.pop, axis=0)).ravel()
            locality_rate = np.asarray(self.pop) * 1.0 / np.asarray(np.sum(self.pop, axis=1)).ravel()[:, None]
            for i in range(m):
                exposure_rs[:, ((i * m) + 0):((i * m) + m)] = np.asarray(locality_rate) * \
                                                              np.asarray(local_expo[:, i]).ravel()[:, None]
        # spatial version loop, uses population intensity
        else:
            local_expo = np.asarray(self.pop) * 1.0 / np.asarray(np.sum(self.pop, axis=0)).ravel()
            locality_rate = np.asarray(self.locality) * 1.0 / np.asarray(np.sum(self.locality, axis=1)).ravel()[:, None]
            for i in range(m):
                exposure_rs[:, ((i * m) + 0):((i * m) + m)] = np.asarray(locality_rate) * \
                                                              np.asarray(local_expo[:, i]).ravel()[:, None]

        # clear nan and inf values and convert to matrix
        exposure_rs[np.isinf(exposure_rs)] = 0
        exposure_rs[np.isnan(exposure_rs)] = 0
        exposure_rs = np.asmatrix(exposure_rs)
        self.local_exposure = exposure_rs

    def cal_globalExposure(self):
        """
        Compute global exposure calling the local version and summing up.
        """
        m = self.n_group
        local_exp = self.local_exposure
        global_exp = np.sum(local_exp, axis=0)
        global_exp = global_exp.reshape((m, m))
        self.global_exposure = global_exp

    def cal_localEntropy(self):
        """
        Compute local entropy score for a unit area Ei (diversity). A unit
        within the metropolitan area, such as a census tract. If population
        intensity was previously computed, the spatial version will be returned,
        otherwise the non spatial version will be selected (raw data).
        """
        # non-spatial version, uses raw data
        if len(self.locality) == 0:
            proportion = np.asarray(self.pop / self.pop_sum)
        # spatial version, uses population intensity
        else:
            proportion = np.asarray(self.locality / self.pop_sum)
        entropy = proportion * np.log(1 / proportion)

        # clear nan and inf values, sum line and reshape
        entropy[np.isnan(entropy)] = 0
        entropy[np.isinf(entropy)] = 0
        entropy = np.sum(entropy, axis=1)
        entropy = entropy.reshape((self.n_location, 1))
        self.local_entropy = entropy

    def cal_globalEntropy(self):
        """
        Compute the global entropy score E (diversity), metropolitan area's entropy score.
        """
        group_score = []
        # non-spatial version, uses raw data
        if len(self.locality) == 0:
            pop_total = np.sum(self.pop_sum)
            prop = np.asarray(np.sum(self.pop, axis=0))[0]
        # spatial version, uses population intensity
        else:
            pop_total = np.sum(self.pop_sum)
            prop = np.asarray(np.sum(self.locality, axis=0))
        for group in prop:
            group_idx = group / pop_total * np.log(1 / (group / pop_total))
            group_score.append(group_idx)

        # sum scores from each group to get the result
        global_entro = np.sum(group_score)
        self.global_entropy = global_entro

    def cal_localIndexH(self):
        """
        Computes the local entropy index H for all localities. The functions
        cal_localEntropy() for local diversity and cal_globalEntropy for global
        entropy are called as input. If population intensity was previously
        computed, the spatial version will be returned, else the non spatial
        version will be selected (raw data).
        """
        local_entropy = self.local_entropy
        global_entropy = self.global_entropy
        # non-spatial version, uses raw data
        if len(self.locality) == 0:
            et = np.asarray(global_entropy * np.sum(self.pop_sum))
            eei = np.asarray(global_entropy - local_entropy)
            h_local = np.asarray(self.pop_sum) * eei / et
        # spatial version, uses population intensity
        else:
            et = np.asarray(global_entropy * np.sum(self.locality))
            eei = np.asarray(global_entropy - local_entropy)
            h_local = np.asarray(self.pop_sum) * eei / et

        self.local_indexh = h_local

    def cal_globalIndexH(self):
        """
        Compute global index H calling the local version summing up.
        """
        h_local = self.local_indexh
        h_global = np.sum(h_local, axis=0)
        self.global_indexh = h_global

    def selectAllMeasures(self):
        """Select all check boxes on measures groups"""
        for button in self.dlg.gbLocal.findChildren(QCheckBox):
            button.setChecked(True)
        for button in self.dlg.gbGlobal.findChildren(QCheckBox):
            button.setChecked(True)

    def runMeasuresButton(self):
        """
        Call the functions to compute local and global measures. The dependency
        complexity is handle by chacking the flaged measures and calling local
        measures for global versions. Results are stored for posterior output save.
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

        # inform sucess if all were computed
        QMessageBox.information(None, "Info", 'Measures computed successfully!')

    def joinResultsData(self):
        """ Join results on a unique matrix and assign names for columns to be
        used as header for csv file and shapefile output"""
        names = ['id','x','y']
        measures_computed = []

        # create new names for groups starting by 0
        for i in range(self.n_group):
            names.append('group_' + str(i))

        # update names with locality if computed
        if len(self.locality) != 0:
            measures_computed.append('self.locality')
            for i in range(self.n_group):
                names.append('intens_' + str(i))

        # update names with exposure/isolation if computed
        if self.dlg.expo_local.isChecked() is True:
            measures_computed.append('self.local_exposure')
            for i in range(self.n_group):
                for j in range(self.n_group):
                    if i == j:
                        names.append('iso_' + str(i) + str(j))
                    else:
                        names.append('exp_' + str(i) + str(j))

        # update names with dissimilarity if computed
        if self.dlg.diss_local.isChecked() is True:
            measures_computed.append('self.local_dissimilarity')
            names.append('dissimil')

        # update names with entropy if computed
        if self.dlg.entro_local.isChecked() is True:
            measures_computed.append('self.local_entropy')
            names.append('entropy')

        # update names with index H if computed
        if self.dlg.idxh_local.isChecked() is True:
            measures_computed.append('self.local_indexh')
            names.append('indexh')

        output_labels = tuple([eval(x) for x in measures_computed])

        # try to concaneta results, else only original input
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
        """Add results to Canvas as a new shapefile based on original input"""
        # get data from layer confirmed on groups selection
        sourceLayer = QgsMapLayerRegistry.instance().mapLayersByName(self.confirmedLayerName)[0]
        sourceFeats = [feat for feat in sourceLayer.getFeatures()]
        sourceGeometryType = ['Point','Line','Polygon'][sourceLayer.geometryType()]
        sourceCRS = sourceLayer.crs().authid()

        # data from results for the new layer
        name = QFileInfo(path).baseName()
        data = result[0][:, (3 + self.n_group):]
        labels = result[1][(3 + self.n_group):]

        # create new layer copying data from source and extend fields
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

    def saveResults(self):
        """ Save results to a local file."""
        try:
            filename = QFileDialog.getSaveFileName(self.dlg, "Select output file ", "", "*.csv")
            self.dlg.leOutput.setText(filename)
            path = self.dlg.leOutput.text()
            result = self.joinResultsData()
            labels = str(', '.join(result[1]))

            # save local measures results on a csv file
            np.savetxt(path, result[0], header=labels, delimiter=',', newline='\n', fmt="%s")

            # add result to canvas as shapefile if requested
            if self.dlg.addToCanvas.isChecked() is True:
                try:
                    self.addShapeToCanvas(result, path)
                except:
                    QMessageBox.critical(None, "Error", "Could not create shape!")
                    return

            # save global results to a second csv file
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
        except:
            QMessageBox.critical(None, "Error", "Could not save data!")
            return

    def run(self):
        """Run method to call dialog and connect interface with functions"""

        # pin view on first tab for attributes selection
        self.dlg.tabWidget.setCurrentIndex(0)

        # clear variables at exit
        self.clearVariables()

        # populate layers list using a projected CRS
        self.addLayers()

        # show the dialog
        self.dlg.show()

        # clear if there is any layer and warn user if not
        if self.dlg.cbLayers.count() == 0:
            QMessageBox.critical(None, "Error", 'No layer found!')
            return

        # Run the dialog event loop
        result = self.dlg.exec_()

        # See if OK was pressed
        if result:
            # exit
            pass
