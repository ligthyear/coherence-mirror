# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright (C) 2006 Fluendo, S.A. (www.fluendo.com).
# Copyright 2006, Frank Scholz <coherence@beebits.net>

import urllib2
import time

from twisted.internet import defer

from coherence.upnp.core.service import Service
from coherence.upnp.core import utils
from coherence import log
from coherence.dispatcher import Dispatcher

import coherence.extern.louie as louie

ns = "urn:schemas-upnp-org:device-1-0"

class Device(Dispatcher):
    logCategory = 'device'
    __signals__ = {'detection_completed': "Sending the information that everything has been detected",
                    'remove_client': "What the hell should I know?"
        }

    def __init__(self, parent=None):
        Dispatcher.__init__(self)
        self.parent = parent
        self.services = []
        #self.uid = self.usn[:-len(self.st)-2]
        self.friendly_name = ""
        self.device_type = ""
        self.friendly_device_type = "[unknown]"
        self.device_type_version = 0
        self.udn = None
        self.client = None
        self.icons = []
        self.devices = []

    def __repr__(self):
        return "embedded device %r %r, parent %r" % \
                (self.friendly_name, self.device_type, self.parent)

    #def __del__(self):
    #    #print "Device removal completed"
    #    pass

    def as_dict(self):
        import copy
        d = {'device_type': self.get_device_type(),
             'friendly_name': self.get_friendly_name(),
             'udn': self.get_id(),
             'services': [x.as_dict() for x in self.services]}
        icons = []
        for icon in self.icons:
            icons.append({"mimetype":icon['mimetype'],
                    "url":icon['url'], "height":icon['height'],
                    "width":icon['width'], "depth":icon['depth']})
        d['icons'] = icons
        return d

    def remove(self, *args):
        self.info("removal of ", self.friendly_name, self.udn)

        devices, self.devices = self.devices, []
        for device in devices:
            self.debug("try to remove %r", device)
            device.remove()

        services, self.services = self.services, []
        for service in services:
            self.debug("try to remove %r", service)
            service.remove()

        if self.client:
            self.emit('remove_client', None, self.udn, self.client)
            self.client = None

    def _completed(self):
        self.debug("checking for completion")
        if self.detection_completed and self.root_detection_completed:
            self.emit('detection_completed', device=self)

    def service_detection_failed(self, device):
        self.remove()

    def get_id(self):
        return self.udn

    def get_uuid(self):
        return self.udn[5:]

    def get_services(self):
        return self.services

    def get_service_by_type(self, type):
        for service in self.services:
            _, _, _, service_class, version = service.service_type.split(':')
            if service_class == type:
                return service

    def add_service(self, service):
        self.debug("add_service %r", service)
        self.services.append(service)
        service.connect("detection_completed",
                self._service_detection_completed)

    def _service_detection_completed(self):
        self._completed_services += 1
        self._completed()

    @property
    def detection_completed(self):
        service_len = len(self.services)
        return  service_len > 0 and service_len == self._completed_services

    def remove_service_with_usn(self, service_usn):
        for service in self.services:
            if service.get_usn() == service_usn:
                self.services.remove(service)
                service.remove()
                break

    def add_device(self, device):
        self.debug("Device add_device %r", device)
        self.devices.append(device)

    def get_friendly_name(self):
        return self.friendly_name

    def get_device_type(self):
        return self.device_type

    def get_friendly_device_type(self):
        return self.friendly_device_type

    def get_markup_name(self):
        try:
            return self._markup_name
        except AttributeError:
            self._markup_name = u"%s:%s %s" % (self.friendly_device_type,
                    self.device_type_version, self.friendly_name)
            return self._markup_name

    def get_device_type_version(self):
        return self.device_type_version

    def set_client(self, client):
        self.client = client

    def get_client(self):
        return self.client

    def renew_service_subscriptions(self):
        """ iterate over device's services and renew subscriptions """
        self.info("renew service subscriptions for %s" % self.friendly_name)
        now = time.time()
        for service in self.services:
            self.info("check service %r %r " % (service.id, service.get_sid()), service.get_timeout(), now)
            if service.get_sid() is not None:
                if service.get_timeout() < now:
                    self.debug("wow, we lost an event subscription for %s %s, " % (self.friendly_name, service.get_id()),
                          "maybe we need to rethink the loop time and timeout calculation?")
                if service.get_timeout() < now + 30 :
                    service.renew_subscription()

        for device in self.devices:
            device.renew_service_subscriptions()

    def unsubscribe_service_subscriptions(self):
        """ iterate over device's services and unsubscribe subscriptions """
        l = []
        for service in self.get_services():
            if service.get_sid() is not None:
                l.append(service.unsubscribe())
        dl = defer.DeferredList(l)
        return dl

    def parse_device(self, d):
        self.info("parse_device %r" %d)
        self.device_type = unicode(d.findtext('./{%s}deviceType' % ns))
        self.friendly_device_type, self.device_type_version = \
                self.device_type.split(':')[-2:]
        self.friendly_name = unicode(d.findtext('./{%s}friendlyName' % ns))
        self.udn = d.findtext('./{%s}UDN' % ns)
        self.info("found udn %r %r" % (self.udn,self.friendly_name))

        try:
            self.manufacturer = d.findtext('./{%s}manufacturer' % ns)
        except:
            pass
        try:
            self.manufacturer_url = d.findtext('./{%s}manufacturerURL' % ns)
        except:
            pass
        try:
            self.model_name = d.findtext('./{%s}modelName' % ns)
        except:
            pass
        try:
            self.model_description = d.findtext('./{%s}modelDescription' % ns)
        except:
            pass
        try:
            self.model_number = d.findtext('./{%s}modelNumber' % ns)
        except:
            pass
        try:
            self.model_url = d.findtext('./{%s}modelURL' % ns)
        except:
            pass
        try:
            self.serial_number = d.findtext('./{%s}serialNumber' % ns)
        except:
            pass
        try:
            self.upc = d.findtext('./{%s}UPC' % ns)
        except:
            pass
        try:
            self.presentation_url = d.findtext('./{%s}presentationURL' % ns)
        except:
            pass

        try:
            for dlna_doc in d.findall('./{urn:schemas-dlna-org:device-1-0}X_DLNADOC'):
                try:
                    self.dlna_dc.append(dlna_doc.text)
                except AttributeError:
                    self.dlna_dc = []
                    self.dlna_dc.append(dlna_doc.text)
        except:
            pass

        try:
            for dlna_cap in d.findall('./{urn:schemas-dlna-org:device-1-0}X_DLNACAP'):
                for cap in dlna_cap.text.split(','):
                    try:
                        self.dlna_cap.append(cap)
                    except AttributeError:
                        self.dlna_cap = []
                        self.dlna_cap.append(cap)
        except:
            pass

        icon_list = d.find('./{%s}iconList' % ns)
        if icon_list is not None:
            import urllib2
            url_base = "%s://%s" % urllib2.urlparse.urlparse(self.get_location())[:2]
            for icon in icon_list.findall('./{%s}icon' % ns):
                try:
                    i = {}
                    i['mimetype'] = icon.find('./{%s}mimetype' % ns).text
                    i['width'] = icon.find('./{%s}width' % ns).text
                    i['height'] = icon.find('./{%s}height' % ns).text
                    i['depth'] = icon.find('./{%s}depth' % ns).text
                    i['realurl'] = icon.find('./{%s}url' % ns).text
                    i['url'] = icon.find('./{%s}url' % ns).text
                    if i['url'].startswith('/'):
                        i['url'] = ''.join((url_base, i['url']))
                    self.icons.append(i)
                    self.debug("adding icon %r for %r" % (i, self.friendly_name))
                except:
                    import traceback
                    self.debug(traceback.format_exc())
                    self.warning("device %r seems to have an invalid icon description, ignoring that icon" % self.friendly_name)

        serviceList = d.find('./{%s}serviceList' % ns)
        if serviceList:
            for service in serviceList.findall('./{%s}service' % ns):
                serviceType = service.findtext('{%s}serviceType' % ns)
                serviceId = service.findtext('{%s}serviceId' % ns)
                controlUrl = service.findtext('{%s}controlURL' % ns)
                eventSubUrl = service.findtext('{%s}eventSubURL' % ns)
                presentationUrl = service.findtext('{%s}presentationURL' % ns)
                scpdUrl = service.findtext('{%s}SCPDURL' % ns)
                """ check if values are somehow reasonable
                """
                if len(scpdUrl) == 0:
                    self.warning("service has no uri for its description")
                    continue
                if len(eventSubUrl) == 0:
                    self.warning("service has no uri for eventing")
                    continue
                if len(controlUrl) == 0:
                    self.warning("service has no uri for controling")
                    continue
                self.add_service(Service(serviceType, serviceId, self.get_location(),
                                         controlUrl,
                                         eventSubUrl, presentationUrl, scpdUrl, self))


            # now look for all sub devices
            embedded_devices = d.find('./{%s}deviceList' % ns)
            if embedded_devices:
                for d in embedded_devices.findall('./{%s}device' % ns):
                    embedded_device = Device(self)
                    self.add_device(embedded_device)
                    embedded_device.parse_device(d)

        self._completed()

    def get_location(self):
        return self.parent.get_location()

    def get_usn(self):
        return self.parent.get_usn()

    def get_upnp_version(self):
        return self.parent.get_upnp_version()

    def get_urlbase(self):
        return self.parent.get_urlbase()

    def get_presentation_url(self):
        try:
            return self.make_fullyqualified(self.presentation_url)
        except:
            return ''

    def get_parent_id(self):
        try:
            return self.parent.get_id()
        except:
            return ''

    def make_fullyqualified(self,url):
        return self.parent.make_fullyqualified(url)

    def as_tuples(self):
        r = []

        def append(name,attribute):
            try:
                if isinstance(attribute,tuple):
                    if callable(attribute[0]):
                        v1 = attribute[0]()
                    else:
                        v1 = getattr(self,attribute[0])
                    if v1 in [None,'None']:
                        return
                    if callable(attribute[1]):
                        v2 = attribute[1]()
                    else:
                        v2 = getattr(self,attribute[1])
                    if v2 in [None,'None']:
                        return
                    r.append((name,(v1,v2)))
                    return
                elif callable(attribute):
                    v = attribute()
                else:
                    v = getattr(self,attribute)
                if v not in [None,'None']:
                    r.append((name,v))
            except:
                import traceback
                self.debug(traceback.format_exc())

        try:
            r.append(('Location',(self.get_location(),self.get_location())))
        except:
            pass
        try:
            append('URL base',self.get_urlbase)
        except:
            pass
        try:
            r.append(('UDN',self.get_id()))
        except:
            pass
        try:
            r.append(('Type',self.device_type))
        except:
            pass
        try:
            r.append(('UPnP Version',self.upnp_version))
        except:
            pass
        try:
            r.append(('DLNA Device Class',','.join(self.dlna_dc)))
        except:
            pass
        try:
            r.append(('DLNA Device Capability',','.join(self.dlna_cap)))
        except:
            pass
        try:
            r.append(('Friendly Name',self.friendly_name))
        except:
            pass
        try:
            append('Manufacturer','manufacturer')
        except:
            pass
        try:
            append('Manufacturer URL',('manufacturer_url','manufacturer_url'))
        except:
            pass
        try:
            append('Model Description','model_description')
        except:
            pass
        try:
            append('Model Name','model_name')
        except:
            pass
        try:
            append('Model Number','model_number')
        except:
            pass
        try:
            append('Model URL',('model_url','model_url'))
        except:
            pass
        try:
            append('Serial Number','serial_number')
        except:
            pass
        try:
            append('UPC','upc')
        except:
            pass
        try:
            append('Presentation URL',('presentation_url',lambda: self.make_fullyqualified(getattr(self,'presentation_url'))))
        except:
            pass

        for icon in self.icons:
            r.append(('Icon', (icon['realurl'],
                               self.make_fullyqualified(icon['realurl']),
                               {'Mimetype': icon['mimetype'],
                                'Width':icon['width'],
                                'Height':icon['height'],
                                'Depth':icon['depth']})))

        return r


class RootDevice(Device):

    def __init__(self, infos):
        self.usn = infos['USN']
        self.server = infos['SERVER']
        self.st = infos['ST']
        self.location = infos['LOCATION']
        self.manifestation = infos['MANIFESTATION']
        self.host = infos['HOST']
        self._completed_services = 0
        self._completed_devices = 0
        Device.__init__(self, None)
        # we need to handle root device completion
        # these events could be ourself or our children.
        self.parse_description()

    def __repr__(self):
        return "rootdevice %r %r %r %r, manifestation %r" % (self.friendly_name,self.udn,self.st,self.host,self.manifestation)

    def get_usn(self):
        return self.usn

    def get_st(self):
        return self.st

    def get_location(self):
        return self.location

    def get_upnp_version(self):
        return self.upnp_version

    def get_urlbase(self):
        return self.urlbase

    def get_host(self):
        return self.host

    def is_local(self):
        if self.manifestation == 'local':
            return True
        return False

    def is_remote(self):
        if self.manifestation != 'local':
            return True
        return False

    def add_device(self, device):
        self.debug("RootDevice add_device %r", device)
        self.devices.append(device)
        device.connect("detection_completed", self._device_completed)

    def _device_complete(self, device):
        self._completed_devices += 1
        self._completed()

    @property
    def root_detection_completed(self):
        devices = len(self.devices)
        return devices == self._completed_devices

    def get_devices(self):
        self.debug("RootDevice get_devices:", self.devices)
        return self.devices

    def parse_description(self):

        def gotPage(x):
            self.debug("got device description from %r" % self.location)
            data, headers = x
            tree = utils.parse_xml(data, 'utf-8').getroot()

            major = tree.findtext('./{%s}specVersion/{%s}major' % (ns,ns))
            minor = tree.findtext('./{%s}specVersion/{%s}minor' % (ns,ns))
            try:
                self.upnp_version = '.'.join((major,minor))
            except:
                self.upnp_version = 'n/a'
            try:
                self.urlbase = tree.findtext('./{%s}URLBase' % ns)
            except:
                import traceback
                self.debug(traceback.format_exc())

            d = tree.find('./{%s}device' % ns)
            if d is not None:
                self.parse_device(d) # root device

        def gotError(failure, url):
            self.warning("error getting device description from %r", url)
            self.info(failure)

        utils.getPage(self.location).addCallbacks(gotPage, gotError, None, None, [self.location], None)

    def make_fullyqualified(self,url):
        if url.startswith('http://'):
            return url
        import urlparse
        base = self.get_urlbase()
        if base != None:
            if base[-1] != '/':
                base += '/'
            r = urlparse.urljoin(base,url)
        else:
            r = urlparse.urljoin(self.get_location(),url)
        return r
