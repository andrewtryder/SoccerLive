###
# Copyright (c) 2013-2014, spline
# All rights reserved.
#
#
###

from supybot.test import *

class SoccerLiveTestCase(ChannelPluginTestCase):
    plugins = ('SoccerLive',)

#    def setUp(self):
#        ChannelPluginTestCase.setUp(self)
#        self.prefix = 'test!test@test'
#        self.nick = 'test'
#        self.irc.feedMsg(ircmsgs.join('#test', prefix='test!test@host'))
#        self.irc.feedMsg(ircmsgs.privmsg(self.irc.nick, ''))

    def testSoccerLive(self):
        self.assertRegexp('soccerchannel add #test World Cup', 'I have added World Cup into #test')
        self.assertRegexp('soccerchannel del #test World Cup', 'I have successfully removed World Cup from #test')


    

# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:
