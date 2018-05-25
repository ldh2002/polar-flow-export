"""
Tool for bulk exporting a range of TCX files from Polar Flow.

exported files are written to the folder "tcx_export" in the current working directory
  
slightly modified version of this command line tool:
https://github.com/gabrielreid/polar-flow-export

Licensed under the Apache Software License v2, see:
    http://www.apache.org/licenses/LICENSE-2.0

Fork: python3
"""

import http.cookiejar
import datetime
import json
import logging
import os
import sys
import time
import tkSimpleDialog
import tkMessageBox
from Tkinter import *import urllib.request, urllib.error, urllib.parse

#------------------------------------------------------------------------------

class ThrottlingHandler(urllib.request.BaseHandler):
    """A throttling handler which ensures that requests to a given host
    are always spaced out by at least a certain number of (floating point)
    seconds.
    """

    def __init__(self, throttleSeconds=1.0):
        self._throttleSeconds = throttleSeconds
        self._requestTimeDict = dict()

    def default_open(self, request):
        hostName = request.host
        
        lastRequestTime = self._requestTimeDict.get(hostName, 0)
        timeSinceLast = time.time() - lastRequestTime
        
        if timeSinceLast < self._throttleSeconds:
            time.sleep(self._throttleSeconds - timeSinceLast)
        self._requestTimeDict[hostName] = time.time()


#------------------------------------------------------------------------------

class TcxFile(object):
    def __init__(self, workout_id, date_str, content):
        self.workout_id = workout_id
        self.date_str = date_str
        self.content = content
# inactive change
# strip away Creator/Author section, so that the TCX-files can be imported to Garmin Connect
# see: https://forums.garmin.com/forum/into-sports/garmin-connect/79753-polar-flow-tcx-export-to-garmin-connect
#        self.content = re.sub(r'<Creator.*</Creator>', '', self.content, flags=re.DOTALL)
#        self.content = re.sub(r'<Author.*</Author>', '', self.content, flags=re.DOTALL)

#------------------------------------------------------------------------------

class PolarFlowExporter(object):

    def __init__(self, username, password):
        self._username = username
        self._password = password
        self._logger = logging.getLogger(self.__class__.__name__)

        self._url_opener = urllib.request.build_opener(
                        ThrottlingHandler(0.5),
                        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self._url_opener.addheaders = [('User-Agent', 
                'https://github.com/ldh2002/polar-flow-export')]
        self._logged_in = False

    def _execute_request(self, path, post_params=None):

        url = "https://flow.polar.com%s" % path

        self._logger.debug("Requesting '%s'" % url)

        if post_params != None:
            postData = urllib.parse.urlencode(post_params).encode("UTF-8")
        else:
            postData = None

        try:
            response = self._url_opener.open(url, postData)
            data = response.read()
        except Exception as e:
            self._logger.error("Error fetching %s: %s" % (url, e))
            raise Exception(e)
        response.close()
        return data  

    def _login(self):
        self._logger.info("Logging in user %s", self._username)
        self._execute_request('/')  # Start a new session
        self._execute_request('/login', 
            dict(returnUrl='https://flow.polar.com/', 
                    email=self._username, password=self._password))
        self._logged_in = True 
        self._logger.info("Successfully logged in")

    def get_tcx_files(self, from_date_str, to_date_str):
        """Returns an iterator of TcxFile objects.

        @param from_date_str an ISO-8601 date string
        @param to_date_str an ISO-8601 date string
        """
        self._logger.info("Fetching TCX files from %s to %s", from_date_str, 
                                                                to_date_str)
        if not self._logged_in:
            self._login()

        # not the most readable or robust solution, but removes dependency 
        # from dateutil which isn't installed on windows by default
        from_date = datetime.date(*(int(x) for x in from_date_str.split("-")))
        to_date = datetime.date(*(int(x) for x in to_date_str.split("-")))

        from_spec = "%s.%s.%s" % (from_date.day, from_date.month, 
                                    from_date.year)

        to_spec = "%s.%s.%s" % (to_date.day, to_date.month, 
                                    to_date.year)

        path = "/training/getCalendarEvents?start=%s&end=%s" % (
                                                        from_spec, to_spec)
        activity_refs = json.loads(self._execute_request(path))


        def get_tcx_file(activity_ref):
            self._logger.info("Retrieving workout %s" 
                                % activity_ref['listItemId'])
            return TcxFile(
                activity_ref['listItemId'],
                activity_ref['datetime'],
                self._execute_request(
                    "%s/export/tcx/false" % activity_ref['url']))

        return (get_tcx_file(activity_ref) for activity_ref in activity_refs)

#------------------------------------------------------------------------------

class GUI(tkSimpleDialog.Dialog):
    def body(self,parent):
        self.entries = {}
        formfields = ["username", "password", "start_date"]
        for label in formfields:
            row = Frame(parent)
            row_label = Label(row, width=10, text=label, anchor='w')
            row_entry = Entry(row, width=30)
            row.pack(side=TOP, padx=10, pady=10)
            row_label.pack(side=LEFT)
            row_entry.pack(side=LEFT)
            self.entries[label] = row_entry
        self.entries["password"].config(show="*")
        self.entries["start_date"].insert(0, "2017-01-31")
        return self.entries["username"].focus()

    def apply(self):
        self.result = self.entries["username"].get(), self.entries["password"].get(), self.entries["start_date"].get()

    def validate(self):
        for label, entry in self.entries.iteritems():
            if len(entry.get()) == 0:
                tkMessageBox.showwarning("Input invalid", "%s can't be empty" % label)
                return 0
        try:
            datetime.date(*(int(x) for x in self.entries["start_date"].get().split("-")))
        except:
            tkMessageBox.showwarning("Input invalid", "Start date has to be entered as YEAR-MONTH-DAY")
            return 0
        return 1

#------------------------------------------------------------------------------

if __name__ == '__main__':

    logging.basicConfig(level=logging.INFO)
    
    root = Tk()
    root.withdraw()
    d = GUI(root)
    try:
        username, password, from_date_str = d.result
    except:
        sys.exit(1)
    to_date_str = str(datetime.date.today())    
    output_dir = "./tcx_export"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    exporter = PolarFlowExporter(username, password)
    for tcx_file in exporter.get_tcx_files(from_date_str, to_date_str):
        filename = "%s_%s.tcx" % (
                        tcx_file.date_str.replace(':', '_'),
                        tcx_file.workout_id)
        output_file = open(os.path.join(output_dir, filename), 'wb')
        output_file.write(tcx_file.content)
        output_file.close()
        print ("Wrote file %s" % filename)

    print ("Export complete")
