# This file is part of Buildbot.  Buildbot is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation, version 2.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51
# Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# Copyright Buildbot Team Members

from zope.interface import implements
from twisted.internet import defer
from buildbot import interfaces
from buildbot.status.buildrequest import BuildRequestStatus

class BuildSetStatus:
    implements(interfaces.IBuildSetStatus)

    def __init__(self, bsdict, status):
        self.id = bsdict['bsid']
        self.bsdict = bsdict
        self.status = status
        self.master = status.master

    # methods for our clients

    def getReason(self):
        return self.bsdict['reason']

    def getResults(self):
        return self.bsdict['results']

    def getID(self):
        return self.bsdict['external_idstring']

    def isFinished(self):
        return self.bsdict['complete']

    def getBuilderNamesAndBuildRequests(self):
        # returns a Deferred; undocumented method that may be removed
        # without warning
        d = self.master.db.buildrequests.getBuildRequests(bsid=self.id)
        def get_objects(brdicts):
            return dict([
                (brd['buildername'], BuildRequestStatus(brd['buildername'],
                                            brd['brid'], self.status))
                for brd in brdicts ])
        d.addCallback(get_objects)
        return d

    def getBuilderNames(self):
        d = self.master.db.buildrequests.getBuildRequests(bsid=self.id)
        def get_names(brdicts):
            return sorted([ brd['buildername'] for brd in brdicts ])
        d.addCallback(get_names)
        return d

    def waitUntilFinished(self):
        return self.status._buildset_waitUntilFinished(self.id)

    def asDict(self):
        d = dict(self.bsdict)
        d["submitted_at"] = str(self.bsdict["submitted_at"])
        return d

class BuildSetSummaryNotifierMixin:
    def summarySubscribe(self):
        self.buildSetSubscription = self.master.subscribeToBuildsetCompletions(self.buildsetFinished)

    def summaryUnsubscribe(self):
        if self.buildSetSubscription is not None:
            self.buildSetSubscription.unsubscribe()
            self.buildSetSubscription = None

    def buildsetFinished(self, bsid, result):
        d = self.master.db.buildsets.getBuildset(bsid=bsid)
        d.addCallback(self._gotBuildSet, bsid)
        return d

    def _gotBuildSet(self, buildset, bsid):
        d = self.master.db.buildrequests.getBuildRequests(bsid=bsid)
        d.addCallback(self._gotBuildRequests, buildset)

    def _gotBuildRequests(self, breqs, buildset):
        dl = []
        for breq in breqs:
            buildername = breq['buildername']
            builder = self.master_status.getBuilder(buildername)
            d = self.master.db.builds.getBuildsForRequest(breq['brid'])
            d.addCallback(lambda builddictlist, builder=builder:
                          (builddictlist, builder))
            dl.append(d)
        d = defer.gatherResults(dl)
        d.addCallback(self._gotBuilds, buildset)

    def includeInSummary(self, build, results):
        return True
    def _gotBuilds(self, res, buildset):
        builds = []
        for (builddictlist, builder) in res:
            for builddict in builddictlist:
                build = builder.getBuild(builddict['number'])
                if build is not None and self.includeInSummary(build, build.results):
                    builds.append(build)

        if builds:
            # We've received all of the information about the builds in this
            # buildset; now send out the summary
            self.sendBuildSetSummary(buildset, builds)
