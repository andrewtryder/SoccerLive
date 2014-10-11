###
# Copyright (c) 2013-2014, spline
# All rights reserved.
#
#
###

from supybot.test import *

class SoccerLiveTestCase(PluginTestCase):
    plugins = ('SoccerLive',)

    def testSoccerLive(self):
        self.assertSnarfResponse('join #test', 'The operation succeeded.')

    

# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:
