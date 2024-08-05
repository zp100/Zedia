import asyncio
import discord
import yt_dlp

from typing import TypeVar
Self = TypeVar("Self", bound="ZediaBot")


# Set up YouTube downloader options.
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'quiet': True,
    'postprocessors': [
        {
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }
    ],
}


class ZediaBot(discord.Client):
    ################################################################
    #                             SETUP                            #
    ################################################################


    def __init__(self: Self, intents: discord.Intents = None):
        super().__init__(intents=intents)

        self.command_queue = []
        self.current_url: str | None = None
        self.audio_queue: list[str] = []
        self.client: discord.VoiceClient | None = None

        self.tc: discord.TextChannel | None = None
        self.vc: discord.VoiceChannel | None = None
        self.me: discord.Member | None = None

        self.is_loading: bool = False
        self.last_message: discord.Message | None = None


    def get_mention(self: Self):
        return f"<@{self.me.id}>"


    async def on_ready(self: Self):
        print(' -- Ready -- ')

        while True:
            if len(self.command_queue) == 0:
                # Check for updates.
                if self.client is None:
                    if len(self.audio_queue) > 0:
                        url = self.audio_queue[0]
                        del self.audio_queue[0]
                        await self.play_audio(url)
                elif not self.client.is_playing():
                    if len(self.audio_queue) > 0:
                        url = self.audio_queue[0]
                        del self.audio_queue[0]
                        await self.play_audio(url)
                    else:
                        self.current_url = None

                await asyncio.sleep(1)
            else:
                cmd, args, ctx = self.command_queue[0].values()
                del self.command_queue[0]

                self.tc = ctx.channel
                self.vc = (ctx.author.voice.channel if ctx.author.voice else None)
                self.me = ctx.guild.me

                # Execute command.
                await cmd(args)


    async def on_message(self: Self, message: discord.Message):
        # Ignore bot's own messages.
        if message.author == message.guild.me:
            self.last_message = message
            return

        # Parse the message.
        tokens = message.content.split()
        self.me = message.guild.me
        if tokens[0] == self.get_mention():
            # Verbose syntax.
            cmd_mapping = {
                'help': self.cmd_help,
                'search': self.cmd_search,
                'go': self.cmd_go,
                'play': self.cmd_play,
                'exit': self.cmd_exit,
                'reload': self.cmd_reload,
                'queue': self.cmd_queue,
                'skip': self.cmd_skip,
                'list-queue': self.cmd_list_queue,
                'clear-queue': self.cmd_clear_queue,
            }

            if (len(tokens) < 2) or (tokens[1] not in cmd_mapping):
                await self.err_command_name()
            else:
                self.command_queue.append({
                    'cmd': cmd_mapping[tokens[1]],
                    'args': tokens[2:],
                    'ctx': message,
                })
        elif tokens[0].startswith('!z'):
            # Concise syntax.
            cmd_mapping = {
                'h': self.cmd_help,
                'f': self.cmd_search,
                'g': self.cmd_go,
                'p': self.cmd_play,
                'x': self.cmd_exit,
                'r': self.cmd_reload,
                'q': self.cmd_queue,
                's': self.cmd_skip,
                'l': self.cmd_list_queue,
                'c': self.cmd_clear_queue,
            }

            if (len(tokens[0]) != 3) or (tokens[0][2] not in cmd_mapping):
                await self.err_command_name()
            else:
                self.command_queue.append({
                    'cmd': cmd_mapping[tokens[0][2]],
                    'args': tokens[1:],
                    'ctx': message,
                })


    async def on_voice_state_update(self: Self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # Disconnect if everyone else has left the voice channel.
        if (self.client is not None) and (len(self.client.channel.members) <= 1):
            self.current_url = None
            self.audio_queue.clear()
            await self.disconnect_vc()


    ################################################################
    #                           COMMANDS                           #
    ################################################################


    async def cmd_help(self: Self, args: list[str]):
        if len(args) != 0:
            await self.err_arg_count()
        else:
            await self.send_help_embed()


    async def cmd_search(self: Self, args: list[str]):
        if len(args) < 1:
            await self.err_arg_count()
        else:
            query = ' '.join(args)
            await self.send_loading_embed()
            search_results = await self.get_search_results(query)
            if search_results is not None:
                await self.send_search_embed(query, search_results)


    async def cmd_go(self: Self, args: list[str]):
        if len(args) < 1:
            await self.err_arg_count()
        else:
            query = ' '.join(args)
            await self.send_loading_embed()
            search_results = await self.get_search_results(query)
            if search_results is not None:
                url = search_results[0]['original_url']
                await self.play_audio(url)


    async def cmd_play(self: Self, args: list[str]):
        if len(args) != 1:
            await self.err_arg_count()
        elif self.vc is None:
            await self.err_not_in_voice_channel()
        else:
            url = args[0]
            await self.play_audio(url)


    async def cmd_exit(self: Self, args: list[str]):
        if len(args) != 0:
            await self.err_arg_count()
        elif self.client is None:
            await self.err_no_voice_client()
        elif self.vc is None:
            await self.err_not_in_voice_channel()
        elif self.client.channel != self.vc:
            await self.err_voice_channel_mismatch()
        else:
            await self.clear_queue()
            await self.stop_audio()
            await self.disconnect_vc()


    async def cmd_reload(self: Self, args: list[str]):
        if len(args) != 0:
            await self.err_arg_count()
        elif self.client is None:
            await self.err_no_voice_client()
        elif self.vc is None:
            await self.err_not_in_voice_channel()
        elif self.client.channel != self.vc:
            await self.err_voice_channel_mismatch()
        else:
            await self.play_audio(self.current_url)


    async def cmd_queue(self: Self, args: list[str]):
        if len(args) != 1:
            await self.err_arg_count()
        elif self.vc is None:
            await self.err_not_in_voice_channel()
        else:
            url = args[0]
            self.audio_queue.append(url)
            await self.send_simple_embed(f"Added \"{url}\" to queue")
            await self.send_simple_embed(f"Length of queue: {len(self.audio_queue)}")


    async def cmd_skip(self: Self, args: list[str]):
        if len(args) != 0:
            await self.err_arg_count()
        elif self.client is None:
            await self.err_no_voice_client()
        elif self.vc is None:
            await self.err_not_in_voice_channel()
        elif self.client.channel != self.vc:
            await self.err_voice_channel_mismatch()
        else:
            await self.stop_audio()


    async def cmd_list_queue(self: Self, args: list[str]):
        if len(args) != 0:
            await self.err_arg_count()
        elif self.client is None:
            await self.err_no_voice_client()
        elif self.vc is None:
            await self.err_not_in_voice_channel()
        elif self.client.channel != self.vc:
            await self.err_voice_channel_mismatch()
        else:
            await self.list_queue()


    async def cmd_clear_queue(self: Self, args: list[str]):
        if len(args) != 0:
            await self.err_arg_count()
        elif self.client is None:
            await self.err_no_voice_client()
        elif self.vc is None:
            await self.err_not_in_voice_channel()
        elif self.client.channel != self.vc:
            await self.err_voice_channel_mismatch()
        else:
            await self.clear_queue()


    ################################################################
    #                            ERRORS                            #
    ################################################################


    async def err_command_name(self: Self):
        await self.send_error_embed('Unrecognized command')


    async def err_arg_count(self: Self):
        await self.send_error_embed('Invalid number of arguments for this command')


    async def err_no_voice_client(self: Self):
        await self.send_error_embed('Not playing audio')


    async def err_not_in_voice_channel(self: Self):
        await self.send_error_embed('You\'re not in a voice channel')


    async def err_voice_channel_mismatch(self: Self):
        await self.send_error_embed('You and the bot aren\'t in the same voice channel')


    async def err_search_failed(self: Self, query: str):
        await self.send_error_embed(f"Failed to load results for \"{query}\"")


    async def err_audio_failed(self: Self, url: str):
        await self.send_error_embed(f"Failed to load audio from \"{url}\"")


    ################################################################
    #                             CHAT                             #
    ################################################################


    async def send_loading_embed(self: Self):
        await self.send_embed(self.get_loading_embed())
        self.is_loading = True


    async def send_simple_embed(self: Self, desc: str):
        await self.send_embed(self.get_simple_embed(desc))


    async def send_help_embed(self: Self):
        await self.send_embed(self.get_help_embed())


    async def send_search_embed(self: Self, query: str, search_results: list[dict]):
        await self.send_embed(self.get_search_embed(query, search_results))


    async def send_playing_embed(self: Self, url: str, info: dict):
        await self.send_embed(self.get_playing_embed(url, info))


    async def send_error_embed(self: Self, desc: str):
        await self.send_embed(self.get_error_embed(desc))


    async def send_embed(self: Self, embed: discord.Embed):
        if self.is_loading:
            await self.last_message.edit(embed=embed)
            self.is_loading = False
        else:
            await self.tc.send(embed=embed)


    def get_loading_embed(self: Self):
        embed = discord.Embed(
            description='Loading...'
        )
        return embed


    def get_simple_embed(self: Self, desc: str):
        embed = discord.Embed(
            description=desc
        )
        return embed


    def get_help_embed(self: Self):
        embed = discord.Embed(
            colour=0x3333CC,
            title='ℹ️ Help'
        )
        embed.add_field(
            name='Show commands',
            value=f"- {self.get_mention()} help\n- !zh",
            inline=False
        )
        embed.add_field(
            name='Search YouTube',
            value=f"- {self.get_mention()} search {{*query*}}\n- !zf {{*query*}}",
            inline=False
        )
        embed.add_field(
            name='Play audio from YouTube search',
            value=f"- {self.get_mention()} go {{*query*}}\n- !zg {{*query*}}",
            inline=False
        )
        embed.add_field(
            name='Play audio from a YouTube URL',
            value=f"- {self.get_mention()} play {{*url*}}\n- !zp {{*url*}}",
            inline=False
        )
        embed.add_field(
            name='Stop bot',
            value=f"- {self.get_mention()} exit\n- !zx",
            inline=False
        )
        embed.add_field(
            name='Reload the current audio',
            value=f"- {self.get_mention()} reload\n- !zr",
            inline=False
        )
        embed.add_field(
            name='Add audio to the queue from a YouTube URL',
            value=f"- {self.get_mention()} queue {{*url*}}\n- !zq {{*url*}}",
            inline=False
        )
        embed.add_field(
            name='Skip to the next URL in the queue',
            value=f"- {self.get_mention()} skip\n- !zs",
            inline=False
        )
        embed.add_field(
            name='List all URLs in the queue',
            value=f"- {self.get_mention()} list-queue\n- !zl",
            inline=False
        )
        embed.add_field(
            name='Clear all URLs from the queue',
            value=f"- {self.get_mention()} clear-queue\n- !zc",
            inline=False
        )
        return embed


    def get_search_embed(self: Self, query: str, search_results: list[dict]):
        embed = discord.Embed(
            colour=0xCCCC33,
            title='🔍 Search Results',
            description=f"To play one of the results, right-click the link and click \"Copy Link\", then use:\n- {self.get_mention()} play {{*link*}}"
        )
        embed.add_field(
            name='Search query',
            value=query,
            inline=False
        )
        results = ''
        index = 1
        for entry in search_results:
            video_link = f"[{entry['title']}]({entry['original_url']})"
            uploader = entry['uploader']
            results += f"{index}. {video_link} by {uploader}\n"
            index += 1
        embed.add_field(
            name='Top Results',
            value=results.strip(),
            inline=False
        )
        return embed


    def get_playing_embed(self: Self, url: str, info: dict):
        embed = discord.Embed(
            colour=0x33CC33,
            title='🔉 Playing'
        )
        embed.add_field(
            name='Source URL',
            value=url,
            inline=False
        )
        embed.add_field(
            name='Title',
            value=info['title'],
            inline=False
        )
        duration_string = info['duration_string']
        duration_string = (f"0{duration_string}" if len(duration_string) <= 1 else duration_string)
        duration_string = (f"0:{duration_string}" if len(duration_string) <= 2 else duration_string)
        embed.add_field(
            name='Duration',
            value=duration_string,
            inline=False
        )
        uploader = info['uploader']
        uploader_link = f"[{info['uploader_id']}]({info['uploader_url']})"
        embed.add_field(
            name='Uploader',
            value=f"{uploader}\n{uploader_link}",
            inline=False
        )
        return embed


    def get_error_embed(self: Self, desc: str):
        desc += f"\n\nUse \"{self.get_mention()} help\" for more info"
        embed = discord.Embed(
            colour=0xCC3333,
            title='🚫 Error',
            description=desc,
        )
        return embed


    ################################################################
    #                             AUDIO                            #
    ################################################################


    async def get_search_results(self: Self, query: str, results_count: int = 5):
        with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ytdl:
            try:
                info = ytdl.extract_info(f"ytsearch{results_count}:{query}", download=False)
            except:
                await self.err_search_failed(query)
                return None
            
        return info['entries']


    async def play_audio(self: Self, url: str):
        if self.vc is None:
            await self.err_not_in_voice_channel()
            return

        # Create an audio source from the URL.
        await self.send_loading_embed()
        with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ytdl:
            try:
                info = ytdl.extract_info(url, download=False)
                source = discord.FFmpegPCMAudio(info['url'])
            except:
                await self.err_audio_failed(url)
                return

        # Connect to the author's voice channel, if needed.
        if self.client is None:
            await self.connect_vc()
        elif self.client.channel != self.vc:
            await self.disconnect_vc()
            await self.connect_vc()

        # Stop any currently-playing audio, if needed.
        self.client.stop()

        # Play the audio.
        self.client.play(source)
        self.current_url = url
        await self.send_playing_embed(url, info)


    async def stop_audio(self: Self):
        if self.client is None:
            await self.err_no_voice_client()
            return
        
        self.client.stop()
        self.current_url = None
        await self.send_simple_embed('Audio stopped')


    async def list_queue(self: Self):
        if len(self.audio_queue) == 0:
            await self.send_simple_embed('Queue is empty')
            return
        
        message = f"Length of queue: {len(self.audio_queue)}\n"
        index = 1
        for url in self.audio_queue:
            message += f"{index}. {url}\n"
            index += 1
        await self.send_simple_embed(message.strip())


    async def clear_queue(self: Self):
        if len(self.audio_queue) == 0:
            await self.send_simple_embed('Queue is empty')
            return
        
        self.audio_queue.clear()
        await self.send_simple_embed('Queue cleared')


    async def connect_vc(self: Self):
        if self.client is not None:
            self.client.stop()

        await self.vc.connect()
        self.client = self.voice_clients[-1]


    async def disconnect_vc(self: Self):
        if self.client is not None:
            self.client.stop()
            await self.client.disconnect()
            self.client = None
