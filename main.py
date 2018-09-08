from models import Deletes, Autoclears, session

import discord
import asyncio
import aiohttp
import time
import sys
import os
import configparser
import json
import logging
from datetime import datetime


class OneLineExceptionFormatter(logging.Formatter):
    def formatException(self, exc_info):
        result = super().formatException(exc_info)
        return repr(result)

    def format(self, record):
        result = super().format(record)
        if record.exc_text:
            result = result.replace("\n", "")
        return result

handler = logging.StreamHandler()
formatter = OneLineExceptionFormatter(logging.BASIC_FORMAT)
handler.setFormatter(formatter)
logger = logging.getLogger()
logger.setLevel(os.environ.get("LOGLEVEL", "INFO"))
logger.addHandler(handler)


class BotClient(discord.AutoShardedClient):
    def __init__(self, *args, **kwargs):
        super(BotClient, self).__init__(*args, **kwargs)

        self.commands = {
            'help' : self.help,
            'info' : self.info,

            'start' : self.autoclear,
            'clear' : self.clear,
            'stop' : self.stop,
            'rules' : self.rules,
        }

        self.config = configparser.SafeConfigParser()
        self.config.read('config.ini')
        self.dbl_token = self.config.get('DEFAULT', 'dbl_token')


    async def on_ready(self):
        logger.info('Logged in as')
        logger.info(self.user.name)
        logger.info(self.user.id)
        logger.info(self.user.avatar)
        logger.info('------------')


    async def on_guild_remove(self, guild):
        await self.send()


    async def on_guild_join(self, guild):
        await self.send()


    async def send(self):
        if not self.dbl_token:
            return

        guild_count = len(self.guilds)

        csession = aiohttp.ClientSession()
        dump = json.dumps({
            'server_count': guild_count
        })

        head = {
            'authorization': self.dbl_token,
            'content-type' : 'application/json'
        }

        url = 'https://discordbots.org/api/bots/stats'
        async with csession.post(url, data=dump, headers=head) as resp:
            logger.info('returned {0.status} for {1}'.format(resp, dump))

        await csession.close()


    async def on_message(self, message):

        clears = session.query(Autoclears).filter(Autoclears.channel == message.channel.id).order_by(Autoclears.time)

        for c in clears:
            if c.user == message.author.id or c.user is None:
                d = Deletes(time=time.time() + c.time, channel=message.channel.id, message=message.id)

                session.add(d)
                session.commit()
                break

        if message.author.bot or message.content is None or message.guild is None:
            return

        try:
            if await self.get_cmd(message):
                logger.info('Command: ' + message.content)
                session.commit()

        except discord.errors.Forbidden:
            try:
                await message.channel.send('No permissions to perform actions.')
            except discord.errors.Forbidden:
                logger.info('Twice Forbidden')


    async def get_cmd(self, message):

        prefix = 'autoclear '

        command = None

        if message.content == self.user.mention:
            await self.commands['info'](message, '')

        if message.content[0:len(prefix)] == prefix:
            command = message.content.split(' ')[1]
            stripped = (message.content + ' ').split(' ', 2)[-1].strip()

        elif self.user.id in map(lambda x: x.id, message.mentions) and len(message.content.split(' ')) > 1:
            command = message.content.split(' ')[1]
            stripped = (message.content + ' ').split(' ', 2)[-1].strip()

        if command is not None:
            if command in self.commands.keys():
                await self.commands[command](message, stripped)
                return True

        return False


    async def help(self, message, stripped):
        await message.channel.send(embed=discord.Embed(title='HELP', description='''

`autoclear start` - Start autoclearing the current channel. Accepts arguments:
\t* User mentions (users the clear applies to- if no mentions, will do all users)
\t* Duration (time in seconds that messages should remain for- defaults to 10s)

\tE.g `autoclear start @JellyWX#2946 5`

`autoclear clear` - Delete message history of specific users. Accepts arguments:
\t* User mention (user to clear history of)

`autoclear rules` - Check the autoclear rules for specified channels. Accepts arguments:
\t* Channel mention (channel to view rules of- defaults to current)

`autoclear stop` - Cancel autoclearing on current channel. Accepts arguments:
\t* User mentions (users to cancel autoclearing for- if no mentions, will do all users)

        '''))


    async def info(self, message, stripped):
        await message.channel.send(embed=discord.Embed(title='INFO', description='''

Welcome to autoclear bot!

Help page: `autoclear help`
Prefixes: @ me or `autoclear`

Invite me to your guild: <insert link>

        '''))


    async def autoclear(self, message, stripped):

        if not message.author.guild_permissions.manage_guild:
            await message.channel.send('You must be a Manager to run this command')
            return

        seconds = 10

        for item in stripped.split(' '): # determin a seconds argument
            try:
                seconds = float(item)
                break
            except ValueError:
                continue

        if message.mentions != []:
            for mention in message.mentions:
                s = session.query(Autoclears).filter_by(channel=message.channel.id, user=mention.id).first()

                if s is None:
                    print('Creating a new autoclear')
                    a = Autoclears(channel=message.channel.id, time=seconds, user=mention.id)
                    sesison.add(a)

                else:
                    print('Editing existing autoclear from {}s to {}s for {}'.format(s.time, seconds, message.author))
                    s.time = seconds

        else:
            s = session.query(Autoclears).filter_by(channel=message.channel.id, user=None).first()

            if s is None:
                print('Creating a new autoclear')
                a = Autoclears(channel=message.channel.id, time=seconds)

                session.add(a)

            else:
                print('Editing existing autoclear from {}s to {}s'.format(s.time, seconds))
                s.time = seconds


    async def rules(self, message, stripped):

        if len(message.channel_mentions) > 0:
            chan = message.channel_mentions[0]
        else:
            chan = message.channel

        rules = session.query(Autoclears).filter(Autoclears.channel == chan.id)

        strings = []

        for r in rules:
            if r.user is None:
                strings.insert(0, '**GLOBAL**: {} seconds'.format(r.time))
            else:
                strings.append('*{}*: {} seconds'.format(message.guild.get_member(r.user), r.time))

        if strings != []:
            await message.channel.send(embed=discord.Embed(title='{} rules'.format(chan.name), description='\n'.join(strings)))
        else:
            await message.channel.send('No rules set for specified channel')


    async def stop(self, message, stripped):

        if not message.author.guild_permissions.manage_guild:
            await message.channel.send('You must be a Manager to run this command')

        elif message.mentions != []:
            for mention in message.mentions:
                s = session.query(Autoclears).filter_by(channel=message.channel.id, user=mention.id).first()

                if s is None:
                    await message.channel.send('Couldn\'t find an autoclear for specified user `{}` in the current channel'.format(mention))

                else:
                    session.query(Autoclears).filter_by(channel=message.channel.id, user=mention.id).delete(synchronize_session='fetch')
                    await message.channel.send('Cancelled autoclear for specified user `{}`'.format(mention))

        else:
            s = session.query(Autoclears).filter_by(channel=message.channel.id, user=None).first()

            if s is None:
                await message.channel.send('Couldn\'t find a global autoclear in the current channel')

            else:
                session.query(Autoclears).filter_by(channel=message.channel.id, user=None).delete(synchronize_session='fetch')
                await message.channel.send('Cancelled global autoclear on current channel')


    async def clear(self, message, stripped):

        if not message.author.guild_permissions.manage_messages:
            await message.channel.send('Admin is required to perform this command')
            return

        if len(message.mentions) == 0:
            await message.channel.send('Please mention users you wish to clear')
            return

        delete_list = []

        async for m in message.channel.history(limit=1000):
            if time.time() - m.created_at.timestamp() >= 1209600 or len(delete_list) > 99:
                break

            if m.author in message.mentions:
                delete_list.append(m)

        await message.channel.delete_messages(delete_list)


    async def deletes(self):
        await self.wait_until_ready()

        while not self.is_closed():

            try:
                dels = []

                for d in session.query(Deletes).filter(Deletes.time <= time.time()):
                    dels.append(d.map_id)

                    message = await self.get_channel(d.channel).get_message(d.message)

                    if message is None or message.pinned:
                        pass
                    else:
                        logger.info('{}: Attempting to auto-delete a message...'.format(datetime.utcnow().strftime('%H:%M:%S')))
                        try:
                            await message.delete()
                        except Exception as e:
                            logger.error('Ln 1049: {}'.format(e))

            except Exception as e:
                logger.error('check_reminders: {}'.format(e))

            if len(dels) > 0:
                session.query(Deletes).filter(Deletes.map_id.in_(dels)).delete(synchronize_session='fetch')

            session.commit()
            await asyncio.sleep(1)

client = BotClient()

client.loop.create_task(client.deletes())
client.run(client.config.get('DEFAULT', 'token'), max_messages=50)
