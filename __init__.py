# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Segreg
                                 A QGIS plugin
 This plugin computes spatial and non spatial segregation measures
                             -------------------
        begin                : 2017-01-25
        copyright            : (C) 2017 by Sandro Sousa / USP-UFABC
        email                : sandrofsousa@gmail.com
        git sha              : $Format:%H$
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
 This script initializes the plugin, making it known to QGIS.
"""


# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load Segreg class from file Segreg.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    #
    from .segreg import Segreg
    return Segreg(iface)
