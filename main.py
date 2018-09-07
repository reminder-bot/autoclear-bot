from models import Deletes, session

import discord
import asyncio
import aiohttp
import time
import sys
import os
import configparser
import json
import logging


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

        self.times = {
            'last_loop' : time.time(),
            'start' : 0,
            'loops' : 0
        }

        self.commands = {
            'help' : self.help,
            'info' : self.info,

            'autoclear' : self.autoclear,
            'clear' : self.clear,
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
        if message.guild is not None and session.query(Server).filter_by(id=message.guild.id).first() is None:

            server = Server(id=message.guild.id, prefix='$', timezone='UTC', language='EN', blacklist={'data': []}, restrictions={'data': []}, tags={}, autoclears={})

            session.add(server)
            session.commit()

        server = None if message.guild is None else session.query(Server).filter_by(id=message.guild.id).first()
        if server is not None and message.channel.id in map(int, server.autoclears.keys()):
            d = Deletes(time=time.time() + server.autoclears[str(message.channel.id)], channel=message.channel.id, message=message.id)

            session.add(d)
            session.commit()

        if message.author.bot or message.content == None:
            return

        try:
            if await self.get_cmd(message, server):
                logger.info('Command: ' + message.content)

        except discord.errors.Forbidden:
            try:
                await message.channel.send(self.get_strings(server, 'no_perms_general'))
            except discord.errors.Forbidden:
                logger.info('Twice Forbidden')


    async def get_cmd(self, message, server):

        prefix = '$' if server is None else server.prefix

        if message.content.startswith('mbprefix'):
            await self.change_prefix(message, ' '.join(message.content.split(' ')[1:]), server)
            return True

        command = ''
        stripped = ''

        if message.content[0:len(prefix)] == prefix:

            command = (message.content + ' ')[len(prefix):message.content.find(' ')]
            stripped = (message.content + ' ')[message.content.find(' '):].strip()

        elif self.user.id in map(lambda x: x.id, message.mentions) and len(message.content.split(' ')) > 1:

            command = message.content.split(' ')[1]
            stripped = (message.content + ' ').split(' ', 2)[-1].strip()

        else:
            return False

        if command in self.commands.keys():
            if server is not None and message.channel.id in server.blacklist['data'] and not message.content.startswith(('{}help'.format(server.prefix), '{}blacklist'.format(server.prefix))):
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'blacklisted')))
                return False

            command_form = self.commands[command]

            if command_form[1] or server is not None:
                if not message.guild.me.guild_permissions.manage_webhooks:
                    await message.channel.send(self.get_strings(server, 'no_perms_webhook'))

                await command_form[0](message, stripped, server)
                return True

            else:
                return False

        else:
            return False


    async def help(self, message, stripped, server):
        await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'help')))


    async def info(self, message, stripped, server):
        await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'info').format(prefix=server.prefix, user=self.user.name)))


    async def autoclear(self, message, stripped, server):

        if not message.author.guild_permissions.manage_guild:
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'admin_required')))
            return

        seconds = 10

        for item in stripped.split(' '): # determin a seconds argument
            try:
                seconds = float(item)
                break
            except ValueError:
                continue

        if len(message.channel_mentions) == 0:
            if message.channel.id in map(int, server.autoclears.keys()):
                del server.autoclears[str(message.channel.id)]
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'autoclear/disable').format(message.channel.mention)))
            else:
                server.autoclears[str(message.channel.id)] = seconds
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'autoclear/enable').format(seconds, message.channel.mention)))

        else:
            disable_all = True
            for i in message.channel_mentions:
                if i.id not in map(int, server.autoclears.keys()):
                    disable_all = False
                server.autoclears[str(i.id)] = seconds


            if disable_all:
                for i in message.channel_mentions:
                    del server.autoclears[str(i.id)]

                await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'autoclear/disable').format(', '.join(map(lambda x: x.name, message.channel_mentions)))))
            else:
                await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'autoclear/enable').format(seconds)))

        session.commit()


    async def clear(self, message, stripped, server):

        if not message.author.guild_permissions.manage_messages:
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'admin_required')))
            return

        if len(message.mentions) == 0:
            await message.channel.send(embed=discord.Embed(description=self.get_strings(server, 'clear/no_argument')))
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
            await asyncio.sleep(5)

client = BotClient()

client.loop.create_task(client.deletes())
client.run(client.config.get('DEFAULT', 'token'), max_messages=50)
