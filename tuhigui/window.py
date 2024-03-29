#!/usr/bin/env python3
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#

from gettext import gettext as _
from gi.repository import Gtk, Gio, GLib, GObject

from .drawingperspective import DrawingPerspective
from .tuhi import TuhiKeteManager
from .config import Config

import logging
import gi
gi.require_version("Gtk", "3.0")

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('window')

MENU_XML = """
<?xml version="1.0" encoding="UTF-8"?>
<interface>
  <menu id="primary-menu">
  <section>
      <item>
        <attribute name="label" translatable="yes">Portrait</attribute>
        <attribute name="action">win.orientation</attribute>
        <attribute name="target">portrait</attribute>
      </item>
      <item>
        <attribute name="label" translatable="yes">Landscape</attribute>
        <attribute name="action">win.orientation</attribute>
        <attribute name="target">landscape</attribute>
      </item>
  </section>
  <section>
      <item>
        <attribute name="label" translatable="yes">Help</attribute>
        <attribute name="action">app.help</attribute>
      </item>
      <item>
        <attribute name="label" translatable="yes">About</attribute>
        <attribute name="action">app.about</attribute>
      </item>
    </section>
  </menu>
</interface>
"""


@Gtk.Template(resource_path="/org/freedesktop/TuhiGui/ui/ErrorPerspective.ui")
class ErrorPerspective(Gtk.Box):
    '''
    The page loaded when we cannot connect to the Tuhi DBus server.
    '''
    __gtype_name__ = "ErrorPerspective"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @GObject.Property
    def name(self):
        return "error_perspective"


@Gtk.Template(resource_path="/org/freedesktop/TuhiGui/ui/SetupPerspective.ui")
class SetupDialog(Gtk.Dialog):
    '''
    The setup dialog when we don't yet have a registered device with Tuhi.
    '''
    __gtype_name__ = "SetupDialog"
    __gsignals__ = {
        'new-device':
            (GObject.SignalFlags.RUN_FIRST, None, (GObject.TYPE_PYOBJECT,)),
    }

    stack = Gtk.Template.Child()
    label_devicename_p1 = Gtk.Template.Child()
    btn_quit = Gtk.Template.Child()

    def __init__(self, tuhi, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tuhi = tuhi
        self._sig = tuhi.connect('unregistered-device', self._on_unregistered_device)
        tuhi.start_search()
        self.device = None

    def _on_unregistered_device(self, tuhi, device):
        tuhi.disconnect(self._sig)

        self.label_devicename_p1.set_text(_(f'Connecting to {device.name}'))
        self.stack.set_visible_child_name('page1')
        self._sig = device.connect('button-press-required', self._on_button_press_required)
        device.register()

    def _on_button_press_required(self, tuhi, device):
        tuhi.disconnect(self._sig)

        self.stack.set_visible_child_name('page2')
        self._sig = device.connect('registered', self._on_registered)

    def _on_registered(self, tuhi, device):
        tuhi.disconnect(self._sig)
        self.device = device
        self.response(Gtk.ResponseType.OK)

    @GObject.Property
    def name(self):
        return "setup_dialog"


@Gtk.Template(resource_path='/org/freedesktop/TuhiGui/ui/MainWindow.ui')
class MainWindow(Gtk.ApplicationWindow):
    __gtype_name__ = 'MainWindow'

    stack_perspectives = Gtk.Template.Child()
    headerbar = Gtk.Template.Child()
    menubutton1 = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._tuhi = TuhiKeteManager()

        action = Gio.SimpleAction.new_stateful('orientation', GLib.VariantType('s'),
                                               GLib.Variant('s', 'landscape'))
        action.connect('activate', self._on_orientation_changed)
        action.set_state(GLib.Variant.new_string(Config.instance().orientation))
        self.add_action(action)

        builder = Gtk.Builder.new_from_string(MENU_XML, -1)
        menu = builder.get_object("primary-menu")
        self.menubutton1.set_menu_model(menu)

        ep = ErrorPerspective()
        self._add_perspective(ep)
        self.stack_perspectives.set_visible_child_name(ep.name)

        # the dbus bindings need more async...
        if not self._tuhi.online:
            self._tuhi.connect('notify::online', self._on_dbus_online)
        else:
            self._on_dbus_online()

    def _on_dbus_online(self, *args, **kwargs):
        logger.debug('dbus is online')

        dp = DrawingPerspective()
        self._add_perspective(dp)
        active = dp
        self.headerbar.set_title(f'Tuhi')
        self.stack_perspectives.set_visible_child_name(active.name)

        if not self._tuhi.devices:
            dialog = SetupDialog(self._tuhi)
            dialog.set_transient_for(self)
            dialog.connect('response', self._on_setup_dialog_closed)
            dialog.show()
        else:
            dp.device = self._tuhi.devices[0]
            active = dp
            self.headerbar.set_title(f'Tuhi - {dp.device.name}')

    def _on_setup_dialog_closed(self, dialog, response):
        device = dialog.device
        dialog.destroy()

        if response != Gtk.ResponseType.OK or device is None:
            self.destroy()
            return

        logger.debug('device was registered')
        self.headerbar.set_title(f'Tuhi - {device.name}')

        dp = self._get_child('drawing_perspective')
        dp.device = device
        self.stack_perspectives.set_visible_child_name(dp.name)

    def _add_perspective(self, perspective):
        self.stack_perspectives.add_named(perspective, perspective.name)

    def _get_child(self, name):
        return self.stack_perspectives.get_child_by_name(name)

    def _on_reconnect_tuhi(self, tuhi):
        self._tuhi = tuhi

    def _on_orientation_changed(self, action, label):
        action.set_state(label)
        Config.instance().orientation = label.get_string()  # this is a GVariant
