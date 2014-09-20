# -*- coding: utf-8 -*-
###
# Copyright (c) 2013-2014, spline
# All rights reserved.
#
#
###
# my libs
import json  # main events.
try:  # xml.
    import xml.etree.cElementTree as ElementTree
except ImportError:
    import xml.etree.ElementTree as ElementTree
from BeautifulSoup import BeautifulSoup
from itertools import chain  # filtering.
import cPickle as pickle  # pickle to save.
import re, htmlentitydefs  # unescape.
from base64 import b64decode  # b64.
from calendar import timegm  # utc time.
import datetime  # utc time.
import pytz
import datetime
import time

# extra supybot libs.
import supybot.conf as conf
import supybot.ircmsgs as ircmsgs
import supybot.schedule as schedule
# supybot libs
import supybot.utils as utils
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
try:
    from supybot.i18n import PluginInternationalization
    _ = PluginInternationalization('SoccerLive')
except:
    # Placeholder that allows to run the plugin on a bot
    # without the i18n module
    _ = lambda x:x

class SoccerLive(callbacks.Plugin):
    """Add the help for "@plugin help SoccerLive" here
    This should describe *how* to use this plugin."""
    threaded = True

    def __init__(self, irc):
        self.__parent = super(SoccerLive, self)
        self.__parent.__init__(irc)
        # initial states for channels.
        self.channels = {}  # dict for channels with values as teams/ids
        self.dupedict = {}  # dupe filter.
        self._loadpickle()  # load saved data.
        # initial states for games operations.
        self.games = self._fetchgames()  # initial.
        self.nextcheck = None  # initial.
        # now schedule our events.
        def checksoccercron():
            try:
                self.checksoccer(irc)
            except Exception, e:
                import traceback
                traceback.print_exc(e)
                self.log.error("cron: ERROR :: {0}".format(e))
                #self.log.error("traceback: {0}".format(tb))
                self.nextcheck = self._utcnow()+72000
        try:  # setup crontab below.
            schedule.addPeriodicEvent(checksoccercron, self.registryValue('checkInterval'), now=True, name='checksoccer')
        except AssertionError:
            try:
                schedule.removeEvent('checksoccer')
            except KeyError:
                pass
            schedule.addPeriodicEvent(checksoccercron, self.registryValue('checkInterval'), now=True, name='checksoccer')

    def die(self):
        try:
            schedule.removeEvent('checksoccer')
        except KeyError:
            pass
        self.__parent.die()

    ######################
    # INTERNAL FUNCTIONS #
    ######################

    def _httpget(self, url):
        """General HTTP resource fetcher."""

        try:
            headers = {"User-Agent":"Mozilla/5.0 (X11; Ubuntu; Linux i686; rv:17.0) Gecko/20100101 Firefox/17.0"}
            page = utils.web.getUrl(url, headers=headers)
            return page
        except Exception, e:
            self.log.error("ERROR: opening {0} message: {1}".format(url, e))
            return None

    def _unescape(self, text):
        """Turn HTML escaped text back into regular text."""

        def fixup(m):
            text = m.group(0)
            if text[:2] == "&#":
                # character reference
                try:
                    if text[:3] == "&#x":
                        return unichr(int(text[3:-1], 16))
                    else:
                        return unichr(int(text[2:-1]))
                except ValueError:
                    pass
            else:
                # named entity
                try:
                    text = unichr(htmlentitydefs.name2codepoint[text[1:-1]])
                except KeyError:
                    pass
            return text # leave as is
        return re.sub("&#?\w+;", fixup, text)

    ###################################
    # LEAGUES/TOURNAMENT DB FUNCTIONS #
    ###################################

    def _leagues(self, league=None):
        """Translates league name to their corresponding id."""

        table = {   "UEFA Champions League":'2',
                    "World Cup":'4',
                    "French Ligue 1":'9',
                    "German Bundesliga":'10',
                    "Dutch Eredivisie":'11',
                    "Italian Serie A":'12',
                    "Portuguese Liga":'14',
                    "Spanish Primera División":'15',
                    #"Swiss Super League":'17',
                    #"Turkish Super Lig":'18',
                    "Major League Soccer":'19',
                    #"USA Women's United Soccer Association":'20',
                    #"Mexican Liga MX":'22',
                    "Barclays Premier League":'23',
                    "English League Championship":'24',
                    #"English League One":'25',
                    #"English League Two":'26',
                    #"English Conference":'27',
                    #"English FA Cup":'40',
                    #"Capital One Cup":'41',
                    #"Johnstone's Paint Trophy":'42',
                    #"English FA Community Shield":'43',
                    "UEFA Cup":'44',
                    #"Scottish Premier League":'45',
                    "International Friendly":'53',
                    "UEFA World Cup Qualifying":'54',
                    "European Championship Qualifying":'56',
                    "FIFA Confederations Cup":'57',
                    "CONCACAF Gold Cup":'59',
                    "Women's World Cup":'60',
                    "World Cup Qualifying":'61',
                    "World Cup Qualifying - AFC":'62',
                    "World Cup Qualifying - CAF":'63',
                    "World Cup Qualifying - CONCACAF":'64',
                    "World Cup Qualifying - CONMEBOL":'65',
                    "World Cup Qualifying - OFC":'66',
                    "World Cup Qualifying - UEFA":'67',
                    "Friendly":'68',
                    #"U.S. Open Cup":'69',
                    #"Women's International Friendly":'70',
                    "Men's Olympic Tournament":'71',
                    "Men's Olympic Qualifying Tournament":'72',
                    #"World Youth Championship":'73',
                    "European Championship":'74',
                    #"Intercontinental Cup":'75',
                    "African Nations Cup":'76',
                    "Spanish Copa del Rey":'80',
                    #"Copa America":'83',
                    #"Russian Premier League":'106',
                    "FIFA Club World Cup":'1932',
                    "German DFB Pokal":'2061',
                    #"Italian Coppa Italia":'2192',
                    "CONCACAF Champions Cup":'2283',
                    #"European Under-21 Championship":'2284',
                    #"U-20 World Cup":'2285',
                    #"World Series of Football":'2286',
                    #"North American SuperLiga":'2287',
                    #"U-17 World Cup":'2288',
                    #"CONCACAF U23 Tournament":'2289',
                    #"United Soccer Leagues":'2292',
                    "CONCACAF Champions League":'2298',
                    "UEFA Europa League":'2310',
                    #"World Football Challenge":'2312'
                    "Copa MX":'2500'
                    }

        # now handle lookups
        if league:  # if we get a league.
            if league in table:  # see if it's in the table.
                return table[league]  # return the id.
            else:  # league not found.
                return None
        else:  # no input
            return table  # return the dict.

    def _leaguekeytoname(self, leagueid):
        """Translates a league id into its name."""

        # reverse k/v of self._teams() table.
        leagues = dict(zip(*zip(*self._leagues().items())[::-1]))
        # return from table.
        return leagues[str(leagueid)]

    def _filterleague(self, lid):
        """True/False function to check if we should filter league matches coming in via JSON."""

        # we have to make sure there are active leagues.
        if len(self.channels) != 0: # we have specific leagues via the channels.
            leagues = set(chain.from_iterable(([v for (k, v) in self.channels.items()])))
        else: # none so I will pick them for the person with the "big 4"
            # German Bundesliga | Italian Serie A | Spanish Primera División | Barclays Premier League | "French Ligue 1"
            leagues = set(["10", "12", "15", "23", "9"])

        # now, with leagues, we need to see if the lid (leagueid) matches and
        if lid in leagues:  # lid matches.
            return False  # false means DONT filter. ie: let it pass
        else:  # reverse is true.
            return True  # do filter. don't let it pass.

    ###########################################
    # INTERNAL CHANNEL POSTING AND DELEGATION #
    ###########################################

    def _post(self, irc, leagueid, message):
        """Posts message to a specific channel."""

        # first check if we have channels.
        if len(self.channels) == 0:  # bail if none.
            self.log.info("_post: ERROR: I have NO channels defined in plugin. You MUST define one.")
            return
        # we do have channels. lets go and check where to put what.
        leagueids = [str(leagueid)] # append 0 so we output ALL. needs to be str.
        postchans = [k for (k, v) in self.channels.items() if __builtins__['any'](z in v for z in leagueids)]
        # iterate over each and post.
        for postchan in postchans:
            try:
                irc.queueMsg(ircmsgs.privmsg(postchan, message))
            except Exception as e:
                self.log.error("ERROR: Could not send {0} to {1}. {2}".format(message, postchan, e))

    ##########################
    # CHANNEL SAVE INTERNALS #
    ##########################

    def _loadpickle(self):
        """Load channel data from pickle."""

        try:
            datafile = open(conf.supybot.directories.data.dirize(self.name()+".pickle"), 'rb')
            try:
                dataset = pickle.load(datafile)
            finally:
                datafile.close()
        except IOError, e:
            self.log.error("_loadpickle :: ERROR :: loading file: {0}".format(e))
            return False
        # restore.
        self.channels = dataset["channels"]
        return True

    def _savepickle(self):
        """Save channel data to pickle."""

        data = {"channels": self.channels}
        try:
            datafile = open(conf.supybot.directories.data.dirize(self.name()+".pickle"), 'wb')
            try:
                pickle.dump(data, datafile)
            finally:
                datafile.close()
        except IOError, e:
            self.log.error("_savepickle :: ERROR :: saving file: {0}".format(e))
            return False
        return True

    ########
    # TIME #
    ########

    def _utcnow(self):
        """Calculate Unix timestamp in GMT."""

        ttuple = datetime.datetime.utcnow().utctimetuple()
        return timegm(ttuple)

    def _convertUTC(self, dtstring):
        """Converts a DT string into UTC one."""
    
        try:
            if dtstring.endswith("PT"):
                naive = datetime.datetime.strptime(dtstring, "%b %d %Y %I:%M %p PT")  
                local = pytz.timezone("US/Pacific")     
            elif dtstring.endswith("ET"):
                naive = datetime.datetime.strptime(dtstring, "%b %d %Y %I:%M %p ET")  
                local = pytz.timezone("US/Eastern")
            elif dtstring.endswith("AM") or dtstring.endswith("PM"):
                if '/' in dstring:  # bail if we see /.
                    return None
                naive = datetime.datetime.strptime(dtstring, "%b %d %Y %I:%M %p")
                local = pytz.timezone("UTC")
            else:  # can't figure it out.
                self.log.info("ERROR: Trying to parse {0} into GMT".format(dtstring))
                return None
            # here we go.
            local_dt = local.localize(naive, is_dst=None)
            utc_dt = local_dt.astimezone(pytz.UTC) # convert from local->utc.
            rtrstr = timegm(utc_dt.utctimetuple())  # return epoch seconds
            rtrstr = int(rtrstr)
            return rtrstr
        except Exception, e:  # they're showing times in GMT now..
            self.log.info("ERROR: Trying to parse {0} into GMT :: {1}".format(dtstring, e))
            return None

    ##################
    # MAIN INTERNALS #
    ##################

    def _fetchgames(self):
        """Main handler for fetching scores."""

        url = b64decode('aHR0cDovL20uZXNwbi5nby5jb20vc29jY2VyL3Njb3JlYm9hcmQ/JndqYj0=')
        html = self._httpget(url)
        if not html:
            self.log.error("ERROR: _scorefetch: Could not open {0}".format(url))
            return None
        
        # main loop.
        try:
            soup = BeautifulSoup(html, convertEntities=BeautifulSoup.HTML_ENTITIES, fromEncoding='utf-8')
            # find our date
            d = soup.find('a', attrs={'class':'inline'}).findNext('b').getText()
            ds = d.split(' ')  # split on string.
            dm, dn = ds[0], ds[1]  # individual.
            dn = dn.zfill(2)  # pad.
            yr = datetime.datetime.now().year  # current year.
            ddiv = "{0} {1} {2}".format(dm, dn, yr)  # reattach.
            # we need to pad the digit if single. Aug 4 -> Aug 04
            # make sure we have it.
            # now grab games.
            gms = soup.findAll('a', attrs={'href':re.compile('.*gamecast.*')})        
            # dict for output.
            d = {}
            # iterate over all games.
            for gm in gms:
                # <a href="gamecast?gameId=402840&amp;lang=EN&amp;wjb=">9:00 AM ET - Valencia vs AS Monaco</a>
                gid = gm['href'].replace('gamecast?gameId=', '').replace('&lang=EN&wjb=', '')  # gamecast?gameId=398931&lang=EN&wjb=
                # league.
                l = gm.findPrevious('b')
                if not l:
                    continue
                # now the match data itself.
                l = l.getText().encode('utf-8')
                # make sure we want the league.
                leaguetitle = self._leagues(l)
                if not leaguetitle:  # if not in the table, pass.
                    continue
                # match data.
                m = gm.getText()
                # we split at ' - ' to determine status.
                m = m.split('(', 1)[0]  # strip TV, if present.
                # ok, we're good. lets determine status.
                if " vs " in m:  # match is later.
                    vsplit = m.split(' - ', 2)
                    status, statustext = 1, None
                    gt = self._convertUTC("{0} {1}".format(ddiv, vsplit[0]))  # mix the date + time.
                    if not gt:  # lets skip if we can't parse.
                        self.log.info("ERROR: I could not _convertUTC: {0} - skipping: {1}".format(gt, m))
                        continue
                    # next, lets try to grab the hometeam.
                    parts = re.split("^(.*?)\svs\s(.*?)$", vsplit[1])
                    if parts:
                        hometeam, awayteam, homescore, awayscore = parts[1], parts[2], 0, 0
                    else:
                        logging.info("ERROR: cannot parse 'vs' string for regex: {0}".format(vsplit[1]))  # log cannot parse.
                        hometeam, homescore, awayteam, awayscore = None, None, None, None
                else:  # game is ongoing, PPD, Abandoned or Final.
                    parts = re.split("^(.*?)\s-\s(.*?)\s(\d+|P)-(\d+|P)\s(.*?)$", m)
                    if len(parts) is not 7:
                        print "Error trying to regex {0}".format(m)
                    else:
                        # now determine status
                        if ((parts[1].startswith("Post")) or (parts[1].startswith("Abandoned")) or (parts[1].startswith("Cancel"))):
                            continue  # lets skip for now but we're not sure if this will work or not.
                        elif (parts[1].startswith("Final")):
                            status = 3
                        else:
                            status = 2
                        # copy the text of status into statustext
                        statustext = parts[1]
                        gt = None
                        hometeam = parts[2]
                        awayteam = parts[5]
                        homescore = int(parts[3])
                        awayscore = int(parts[4])
                # construct the dict so we may return.
                d[gid] = {  'status': status,  # 1, 2, 3 (int)
                            'gametime': gt,  # epoch int
                            'statustext': statustext,  # FT, HT, '45 (min)
                            'hometeam': hometeam.strip().encode('utf-8'),
                            'homescore': homescore,
                            'awayteam': awayteam.strip().encode('utf-8'),
                            'awayscore': awayscore,
                            'league': leaguetitle }  # league id.
    
            # prepare for returning output.
            tmp = d  # container for output.
            return tmp
        except Exception, e:
            self.log.error("_scorefetch: ERROR (exception) :: {0}".format(e))
            return None

    def _gameevent(self, gid, golnum):
        """Fetches events from match and tries to return the goal # based on score."""

        url = b64decode('aHR0cDovL2VzcG5mYy5jb20vZ2FtZXBhY2thZ2UxMC9kYXRhL3RpbWVsaW5lP2dhbWVJZD0=') + str(gid)
        html = self._httpget(url)
        if not html:
            self.log.error("ERROR: _gameevent: Could not open {0}".format(url))
            return None
        # process.
        try:
            html = html.decode('iso-8859-1')  # odd encoding but whatever.
            tree = ElementTree.fromstring(html)  # process XML. listcmp goals below and cleanup.
            goals = tree.findall('./events/event[@type="goal"]')  # find all goal events in XML.
            # test to make sure we found something.
            if len(goals) == 0:
                self.log.error("ERROR: _gameevent: no scoring events found in {0}".format(gid))
                return None
            else:  # we found something. figure out the team and goal.
                # warning: if golnum is NOT found, it will throw a list index error (fine)
                hora = goals[golnum].get('side')  # figure out the side. (home or away)
                goalteam = self._ec(tree.find(hora).text)  # translate the side into the team name.
                goaltext = self._ec(goals[golnum].find('result').text)  # grab goaltext. cleanup and encode.
                goalstr = "GOL :: {0} :: {1}".format(goalteam, goaltext)  # construct string to return.
                return goalstr
        except Exception, e:
            self.log.error("_gameevent: ERROR (exception) from {0} :: {1}".format(gid, e))
            return None

    def _ec(self, txt):
        """Cleans up events and team names for output."""

        txt = self._unescape(txt)  # htmlentity -> text
        # now clean up the html
        txt = txt.replace('<b>', '').replace('</b>', '').replace('<br>', ' ')
        # return unicode.
        return txt.encode('utf-8')

    ####################
    # PUBLIC FUNCTIONS #
    ####################

    def soccerchannel(self, irc, msg, args, op, optchannel, optarg):
        """<add|list|del> <#channel> <ALL|league>

        Add or delete league or tournament from a specific channel's output.
        Can only specify one at a time and you must use the league's name with proper capitalization. See leagues.
        Ex: #channel1 ALL OR #channel2 World Cup
        """

        # first, lower operation.
        op = op.lower()
        # next, make sure op is valid.
        validop = ['add', 'list', 'del', 'leagues']
        if op not in validop:  # test for a valid operation.
            irc.reply("ERROR: '{0}' is an invalid operation. It must be be one of: {1}".format(op, " | ".join([i for i in validop])))
            return
        # if we're not doing list (add or del) make sure we have the arguments.
        if ((op != 'list') and (op != 'leagues')):
            if not optchannel and not optarg:  # add|del need these.
                irc.reply("ERROR: add and del operations require a channel and team. Ex: add #channel World Cup OR del #channel World Cup")
                return
            # we are doing an add/del op.
            optchannel = optchannel.lower()
            # make sure channel is something we're in
            if op == 'add':  # only check for add operations.
                if optchannel not in irc.state.channels:
                    irc.reply("ERROR: '{0}' is not a valid channel. You must add a channel that we are in.".format(optchannel))
                    return
            # test for valid team now.
            leagueid = self._leagues(league=optarg)
            if not leagueid:  # invalid arg(team)
                irc.reply("ERROR: '{0}' is an invalid team/argument. See soccerchannel list for a valid list.".format(optarg))
                return
        # main meat part.
        # now we handle each op individually.
        if op == 'add':  # add output to channel.
            self.channels.setdefault(optchannel, set()).add(leagueid)  # add it.
            self._savepickle()  # save.
            irc.reply("I have added {0} into {1}".format(optarg, optchannel))
        elif op == 'leagues':  # list leagues
            irc.reply("Valid leagues: {0}".format(" | ".join([l for l in sorted(self._leagues().keys())])))
        elif op == 'list':  # list channels
            if len(self.channels) == 0:  # no channels.
                irc.reply("ERROR: I have no active channels defined. Please use the soccerchannel add operation to add a channel.")
            else:   # we do have channels.
                for (k, v) in self.channels.items():  # iterate through and output translated keys.
                    irc.reply("{0} :: {1}".format(k, " | ".join([self._leaguekeytoname(leagueid=q) for q in v])))
        elif op == 'del':  # delete an item from channels.
            if optchannel in self.channels:
                if leagueid in self.channels[optchannel]:  # id is already in.
                    self.channels[optchannel].remove(leagueid)  # remove it.
                    # now check if it's the last item. we should remove the channel then.
                    if len(self.channels[optchannel]) == 0:  # none left.
                        del self.channels[optchannel]  # delete the channel key.
                    self._savepickle()  # save.
                    irc.reply("I have successfully removed {0} from {1}".format(optarg, optchannel))
                else:  # id was NOT in there.
                    irc.reply("ERROR: I do not have {0} in {1}".format(optarg, optchannel))
            else:
                irc.reply("ERROR: I do not have {0} in {1}".format(optarg, optchannel))

    soccerchannel = wrap(soccerchannel, [('checkCapability', 'admin'), ('somethingWithoutSpaces'), optional('channel'), optional('text')])

    ################################
    # EVENT HANDLERS AND DELEGATES #
    ################################

    def _ft(self, ev):
        """Handle formatting of match going to FT."""

        leaguename = self._leaguekeytoname(leagueid=ev['league'])
        mstr = "FT :: {0} {1}-{2} {3} - {4}".format(ev['hometeam'], ev['homescore'], ev['awayscore'], ev['awayteam'], leaguename)
        return mstr

    def _ht(self, ev):
        """Handle formatting of match going to HT."""

        mstr = "HT :: {0} {1}-{2} {3}".format(ev['hometeam'], ev['homescore'], ev['awayscore'], ev['awayteam'])
        return mstr

    def _kickoff2(self, ev):
        """Handle formatting of kickoff in 2nd half."""

        mstr = "2H KICKOFF :: {0} {1}-{2} {3}".format(ev['hometeam'], ev['homescore'], ev['awayscore'], ev['awayteam'])
        return mstr


    def _kickoff(self, ev):
        """Handle formatting of match kickoff."""

        leaguename = self._leaguekeytoname(leagueid=ev['league'])
        mstr = "KICKOFF :: {0} v. {1} :: {2}".format(ev['hometeam'], ev['awayteam'], leaguename)
        return mstr

    def _goalscored(self, ev):
        """Handle formatting of a goal."""

        mstr = "{0} {1} - {2} {3}".format(ev['hometeam'], ev['homescore'], ev['awayscore'], ev['awayteam'])
        return mstr

    ###################
    # DUPEDICT SYSTEM #
    ###################

    def _dupedict(self, k, m):
        """Horrid stopgap to stop dupes from being printed."""

        if k in self.dupedict:  # channel is already present. this is required.
            if m in self.dupedict[k]:  # if m is already present, we've printed it.
                self.log.error("_dupedict: ERROR. {0} tried to reprint {1}".format(k, m))
                return False
            else:  # k is present but m is not (message not printed). This is good.
                self.dupedict[k].add(m)  # add message to set.
                return True
        else:  # channel is not present in dupedict. something went wrong.
            self.log.info("_dupedict: {0} not in dupedict. I tried to print: {1}".format(k, m))
            return False

    ################
    # MAIN COMMAND #
    ################

    #def soccercheck(self, irc, msg, args):
    #    """
    #    Debug.
    #    """
    #
    #    irc.reply("NEXTCHECK: {0}".format(self.nextcheck))
    #
    #    for (k, v) in self.games.items():
    #        irc.reply("{0} :: {1}".format(k, v))
    #    irc.reply("DUPEDICT {0}".format(len(self.dupedict)))
    #    for (k, v) in self.dupedict.items():
    #        irc.reply("{0} :: {1}".format(k, v))
    #
    #soccercheck = wrap(soccercheck)

    def socceron(self, irc, msg, args, channel):
        """
        Re-enable soccer updates in channel.
        Must be enabled by an op in the channel scores are already enabled for.
        """

        # channel
        channel = channel.lower()
        # check if op.
        if not irc.state.channels[channel].isOp(msg.nick):
            irc.reply("ERROR: You must be an op in this channel for this command to work.")
            return
        # check if channel is already on.
        if channel in self.channels:
            irc.reply("ERROR: {0} is already enabled for soccer updates.".format(channel))
        # we're here if it's not. let's re-add whatever we have saved.
        # most of this is from _loadchannels
        try:
            datafile = open(conf.supybot.directories.data.dirize(self.name()+".pickle"), 'rb')
            try:
                dataset = pickle.load(datafile)
            finally:
                datafile.close()
        except IOError, e:
            irc.reply("ERROR: I could not open the soccer pickle to restore :: {0}".format(e))
            return
        # now check if channels is in the dataset from the pickle.
        if channel in dataset['channels']:  # it is. we're good.
            self.channels[channel] = dataset['channels'][channel]  # restore it.
            irc.reply("I have successfully restored updates to: {0}".format(channel))
        else:
            irc.reply("ERROR: {0} is not in the saved channel list. Please use soccerchannel to add it.".format(channel))

    socceron = wrap(socceron, [('channel')])

    def socceroff(self, irc, msg, args, channel):
        """
        Disable soccer scoring updates in a channel.
        Must be issued by an op in a channel it is enabled for.
        """

        # channel
        channel = channel.lower()
        # check if op.
        if not irc.state.channels[channel].isOp(msg.nick):
            irc.reply("ERROR: You must be an op in this channel for this command to work.")
            return
        # check if channel is already on.
        if channel not in self.channels:
            irc.reply("ERROR: {0} is not in self.channels. I can't disable updates for a channel I don't update in.".format(channel))
            return
        else:  # channel is in the dict so lets do a temp disable by deleting it.
            del self.channels[channel]
            irc.reply("I have successfully disabled soccer updates in {0}".format(channel))

    socceroff = wrap(socceroff, [('channel')])


    def checksoccer(self, irc):
    #def checksoccer(self, irc, msg, args):
        """
        Main loop.
        """

        self.log.info("Starting check..")

        # before anything, check if we should backoff first.
        if self.nextcheck:
            utcnow = self._utcnow()
            if self.nextcheck > utcnow:  # in the future.
                self.log.info("checksoccer: nextcheck is in {0}s.".format(self.nextcheck-utcnow))
                return
            else:  # in the past so lets reset it and continue.
                self.nextcheck = None
        # if it's our first run, or the initial run yielded None, we try again.
        if not self.games:
            self.games = self._fetchgames()
        # last chance. bail otherwise and wait until nexttime.
        if not self.games:
            self.log.error("checksoccer: missing self.games. bailing.")
            return
        else:  # we do have initial games so we copy to games1/ssid1
            games1 = self.games
        # we have games1. lets grab new games. we only try once.
        games2 = self._fetchgames()
        if not games2:  # if we don't have new, can't compare old so we bail.
            self.log.error("checksoccer: missing games2. bailing.")
            return

        # the main part. we compare games1 (old) and games2 (new), firing necessary events.
        for (k, v) in games1.items():  # iterate through self.games.
            #self.log.info("k: {0} v: {1}".format(k, v))
            if k in games2:  # match up keys because we don't know the frequency of the games/list changing.
                # HANDLE KICKOFF.
                if ((v['status'] == 1) and (games2[k]['status'] == 2)):  # 1->2 = kickoff.
                    self.log.info("checksoccer: kickoff {0}".format(k))
                    # grab the kickoff message, post to irc, and create entry in dupedict.
                    mstr = self._kickoff(games2[k])
                    #self._post(irc, v['league'], mstr)
                    # we start our foray into dupedict here by creating it.
                    if k not in self.dupedict:  # this means k is not in dupedict, which is good, so we enter it to allow events to be posted.
                        self.log.info("KICKOFF Putting {0} into dupedict and posting kickoff.".format(k))
                        self.dupedict[k] = set([mstr])  # add it and post.
                        self._post(irc, v['league'], mstr)
                    else:
                        self.log.info("ERROR: KICKOFF {0} is already in dupedict?".format(k))
                # ACTIVE GAME EVENTS ONLY.
                #if ((v['status'] == 2) and (games2[k]['status'] == 2)):
                if (v['status'] == 2):
                    # make sure k is in dupedict (incase we restart). this might be buggy?
                    #if k not in self.dupedict:
                    #    self.log.info("{0} is an active game but not in dupedict. We're adding it with an empty set.".format(k))
                    #    self.dupedict[k] = set([])
                    # SCORING EVENT.
                    if ((v['awayscore'] < games2[k]['awayscore']) or (v['homescore'] < games2[k]['homescore'])):
                        self.log.info("Should be firing scoring event from {0}".format(k))
                        #self.log.info("OLD: {0}".format(v))
                        #self.log.info("NEW: {0}".format(games2[k]))
                        # before we grab the event, we need to figure out what event # to grab and subtract 1 for list index.
                        scoretotal = (games2[k]['awayscore']+games2[k]['homescore'])-1
                        # try and grab the specific scoring event from XML.
                        scoreevent = self._gameevent(k, scoretotal)
                        if scoreevent:  # we get the scoring (XML) event back and the proper index.
                            mstr = "{0} :: {1}".format(self._goalscored(games2[k]), scoreevent)
                        else:  # we either got NO scoring event back or the wrong index number. lets just print the team who scored + statustext (minute).
                            # figure out what team scored.
                            if abs(games2[k]['homescore'] - v['homescore']) == 0:  # htdiff = 0, so awayteam scored.
                                scoreteam = v['awayteam']
                            else:  # htscorediff != 0, so hometeam scored.
                                scoreteam = v['hometeam']
                            # now lets construct string.
                            mstr = "{0} :: GOL :: {1} :: {2}".format(self._goalscored(games2[k]), scoreteam, games2[k]['statustext'])
                        #self._post(irc, v['league'], mstr)
                        # test if it's a dupe.
                        testdupe = self._dupedict(k, mstr)  # dupetest.
                        if testdupe:  # returned True so we print it.
                            self._post(irc, v['league'], mstr)
                    # GAME GOES TO HT.
                    if ((v['statustext'] != games2[k]['statustext']) and (games2[k]['statustext'] == 'Half')):
                        self.log.info("Should be firing HT in {0}".format(k))
                        # grab HT event and print.
                        mstr = self._ht(games2[k])
                        #self._post(irc, v['league'], mstr)
                        # test if it's a dupe.
                        testdupe = self._dupedict(k, mstr)  # dupetest.
                        if testdupe:  # returned True so we print it.
                            self._post(irc, v['league'], mstr)
                    # GAME RESUMES FROM HT.
                    if ((v['statustext'] != games2[k]['statustext']) and (v['statustext'] == 'Half')):
                        self.log.info("Should be firing 2H kickoff from {0}".format(k))
                        # grab 2H KICKOFF event and print.
                        mstr = self._kickoff2(games2[k])
                        #self._post(irc, v['league'], mstr)
                        # test if it's a dupe.
                        testdupe = self._dupedict(k, mstr)  # dupetest.
                        if testdupe:  # returned True so we print it.
                            self._post(irc, v['league'], mstr)
                # GAME GOES TO FT.
                if ((v['status'] == 2) and (games2[k]['status'] == 3)):  # 2->3 is FT.
                    self.log.info("checksoccer: FT {0}".format(k))
                    # grab FT message and print.
                    mstr = self._ft(games2[k])
                    #self._post(irc, v['league'], mstr)
                    # test if it's a dupe.
                    testdupe = self._dupedict(k, mstr)  # dupetest.
                    if testdupe:  # returned True so we print it.
                        self._post(irc, v['league'], mstr)
                    # now that we're done printing the final part of the game, delete the key so we can't print more.
                    if k in self.dupedict:
                        self.log.info("FT DELETING {0} from dupedict".format(k))
                        del self.dupedict[k]

        # we're done processing games and output. we need to now prepare ourselves for the next check.
        # we grab game statuses to figure out if games are going on or not.
        #self.log.info("done checking.")
        self.games = games2
        # now get our gamestatuses.
        gamestatuses = set([v['status'] for (k, v) in games2.items()])  # grab statuses from newest games.
        self.log.info("GS: {0}".format(gamestatuses))
        if 2 not in gamestatuses:  # no active games. (1, 3 only)
            # here, we have two checks for if 1 (future games) are present or not.
            # if we have no games in the future, all 3, we need to backoff.
            # otherwise, nextcheck is set based on firstgametime.
            utcnow = self._utcnow()  # grab UTC now.
            # now check if we have all FT (3, no 1 or 2).
            if 1 not in gamestatuses:  # (only 3) Backoff 10 minutes.
                self.log.info("checksoccer: all games are 3. backing off 10 minutes.")
                self.nextcheck = utcnow+600
            else:  # we have future games.
                firstgametime = sorted([v['gametime'] for (k, v) in games2.items() if v['status'] == 1])[0]  # first startdate.
                # now check if this has past or not.
                if utcnow > firstgametime:  # something is stale like when a game has a 2000 starttime but kicks off at 2005
                    self.nextcheck = utcnow+60
                    self.log.info("checksoccer: firstgametime has passed. backing off 60 seconds.")
                else:  # first game time is in the future.
                    self.log.info("checksoccer: firstgametime is in the future. {0} seconds from now".format(firstgametime-utcnow))
                    self.nextcheck = firstgametime  # set.
        else:  # we're processing active games.
            self.nextcheck = None  # erase.

    #checksoccer = wrap(checksoccer)

Class = SoccerLive


# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:
