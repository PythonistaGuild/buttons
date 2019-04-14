import asyncio
import discord
import inspect
from discord.ext import commands
from functools import partial
from typing import Union


class Session:
    """Interactive session class, which uses reactions as buttons.

    timeout: int
        The timeout in seconds to wait for reaction responses.
    try_remove: bool
        A bool indicating whether or not the session should try to remove reactions after they have been pressed.
    """

    def __init__(self, *, timeout: int = 180, try_remove: bool = True):
        self._buttons = {}
        self._gather_buttons()

        self.page: discord.Message = None
        self._session_task = None
        self._cancelled = False
        self._try_remove = try_remove

        self.timeout = timeout
        self.buttons = self._buttons

    def __init_subclass__(cls, **kwargs):
        pass

    def _gather_buttons(self):
        for _, member in inspect.getmembers(self):
            if hasattr(member, '__button__'):  # Check if the member is a button...
                self._buttons[member.__button__[2], member.__button__[0]] = member.__button__[1]  # pos, key, value

    def sort_buttons(self, *, buttons: dict = None):
        if not buttons:
            buttons = self.buttons

        return {k[1]: v for k, v in sorted(buttons.items(), key=lambda t: t[0])}

    async def start(self, ctx, page=None):
        """Start the session with the given page.

        Parameters
        -----------
        page: Optional[str, discord.Embed, discord.Message]
            If no page is given, the message used to invoke the command will be used. Otherwise if
            an embed or str is passed, a new message will be created.
        """
        if not page:
            page = ctx.message

        if isinstance(page, discord.Embed):
            self.page = await ctx.send(embed=page)
        elif isinstance(page, discord.Message):
            self.page = page
        else:
            self.page = await ctx.send(page)

        self._session_task = ctx.bot.loop.create_task(self._session(ctx))

    async def _session(self, ctx):
        self.buttons = self.sort_buttons()

        for reaction in self.buttons.keys():
            ctx.bot.loop.create_task(self._add_reaction(reaction))

        while True:
            try:
                payload = await ctx.bot.wait_for('raw_reaction_add', timeout=self.timeout,
                                                 check=lambda _: self.check(_)(ctx))
            except asyncio.TimeoutError:
                return ctx.bot.loop.create_task(self.cancel(ctx))

            if self._try_remove:
                try:
                    await self.page.remove_reaction(payload.emoji, ctx.guild.get_member(payload.user_id))
                except discord.HTTPException:
                    pass

            emoji = self.get_emoji_as_string(payload.emoji)
            action = self.buttons[emoji]

            await action(self, ctx)

    @property
    def is_cancelled(self):
        """Return True if the session has been cancelled."""
        return self._cancelled

    async def cancel(self, ctx):
        """Cancel the session."""
        self._cancelled = True
        await self.teardown(ctx)

    async def teardown(self, ctx):
        """Clean the session up."""
        self._session_task.cancel()
        await self.page.delete()

    async def _add_reaction(self, reaction):
        await self.page.add_reaction(reaction)

    def get_emoji_as_string(self, emoji):
        return f'{emoji.name}{":" + str(emoji.id) if emoji.is_custom_emoji() else ""}'

    def check(self, payload):
        """Check which takes in a raw_reaction payload. This may be overwritten."""
        emoji = self.get_emoji_as_string(payload.emoji)

        def inner(ctx):
            if emoji not in self.buttons.keys():
                return False
            elif payload.user_id == ctx.bot.user.id or payload.message_id != self.page.id:
                return False
            elif payload.user_id != ctx.author.id:
                return False
            return True

        return inner


class Paginator(Session):
    """Paginator class, that used an interactive session to display buttons.

    title: str
        Only available when embed=True. The title of the embeded pages.
    length: int
        The number of entries per page.
    entries: list
        The entries to paginate.
    extra_pages: list
        Extra pages to append to our entries.
    prefix: Optional[str]
        The formatting prefix to apply to our entries.
    suffix: Optional[str]
        The formatting suffix to apply to our entries.
    format: Optional[str]
        The format string to wrap around our entries. This should be the first half of the format only,
        E.g to wrap **Entry**, we would only provide **.
    colour: discord.Colour
        Only available when embed=True. The colour of the embeded pages.
    use_defaults: bool
        Option which determines whether we should use default buttons as well. This is True by default.
    embed: bool
        Option that indicates that entries should embeded.
    joiner: str
        Option which allows us to specify the entries joiner. E.g self.joiner.join(self.entries)
    timeout: int
        The timeout in seconds to wait for reaction responses.
    thumbnail:
        Only available when embed=True. The thumbnail URL to set for the embeded pages.
    """

    def __init__(self, *, title: str = '', length: int = 10, entries: list = None,
                 extra_pages: list = None, prefix: str = '', suffix: str = '', format: str = '',
                 colour: Union[int, discord.Colour] = discord.Embed.Empty,
                 color: Union[int, discord.Colour] = discord.Embed.Empty, use_defaults: bool = True, embed: bool = True,
                 joiner: str = '\n', timeout: int = 180, thumbnail: str = None):
        super().__init__()
        self._defaults = {(0, '⏮'): partial(self._default_indexer, 'start'),
                          (1, '◀'): partial(self._default_indexer, -1),
                          (2, '⏹'): partial(self._default_indexer, 'stop'),
                          (3, '▶'): partial(self._default_indexer, +1),
                          (4, '⏭'): partial(self._default_indexer, 'end')}

        self.buttons = {}

        self.page: discord.Message = None
        self._pages = []
        self._session_task = None
        self._cancelled = False
        self._index = 0

        self.title = title
        self.colour = colour or color
        self.thumbnail = thumbnail
        self.length = length
        self.timeout = timeout
        self.entries = entries
        self.extra_pages = extra_pages or []

        self.prefix = prefix
        self.suffix = suffix
        self.format = format
        self.joiner = joiner
        self.use_defaults = use_defaults
        self.use_embed = embed

    def chunker(self):
        """Create chunks of our entries for pagination."""
        for x in range(0, len(self.entries), self.length):
            yield self.entries[x:x + self.length]

    def formatting(self, entry: str):
        """Format our entries, with the given options."""
        return f'{self.prefix}{self.format}{entry}{self.format[::-1]}{self.suffix}'

    async def start(self, ctx: commands.Context, page=None):
        """Start our Paginator session."""
        if not self.use_defaults:
            if not self._buttons:
                raise AttributeError('Session has no buttons.')  # Raise a custom exception at some point.

        await self._paginate(ctx)

    async def _paginate(self, ctx: commands.Context):
        if not self.entries and not self.extra_pages:
            raise AttributeError('You must provide atleast one entry or page for pagination.')  # ^^

        if self.entries:
            self.entries = [self.formatting(entry) for entry in self.entries]
            entries = list(self.chunker())
        else:
            entries = []

        for chunk in entries:
            if not self.use_embed:
                self._pages.append(self.joiner.join(chunk))
            else:
                embed = discord.Embed(title=self.title, description=self.joiner.join(chunk), colour=self.colour)

                if self.thumbnail:
                    embed.set_thumbnail(url=self.thumbnail)

                self._pages.append(embed)

        self._pages = self._pages + self.extra_pages

        if isinstance(self._pages[0], discord.Embed):
            self.page = await ctx.send(embed=self._pages[0])
        else:
            self.page = await ctx.send(self._pages[0])

        self._session_task = ctx.bot.loop.create_task(self._session(ctx))

    async def _session(self, ctx):
        if self.use_defaults:
            self.buttons = {**self._defaults, **self._buttons}
        else:
            self.buttons = self._buttons

        self.buttons = self.sort_buttons()

        for reaction in self.buttons.keys():
            ctx.bot.loop.create_task(self._add_reaction(reaction))

        while True:
            try:
                payload = await ctx.bot.wait_for('raw_reaction_add', timeout=self.timeout,
                                                 check=lambda _: self.check(_)(ctx))
            except asyncio.TimeoutError:
                return ctx.bot.loop.create_task(self.cancel(ctx))

            if self._try_remove:
                try:
                    await self.page.remove_reaction(payload.emoji, ctx.guild.get_member(payload.user_id))
                except discord.HTTPException:
                    pass

            emoji = self.get_emoji_as_string(payload.emoji)
            action = self.buttons[emoji]

            if action in self._defaults.values():
                await action(ctx)
            else:
                await action(self, ctx)

    async def _default_indexer(self, control, ctx):
        previous = self._index

        if control == 'stop':
            return await self.cancel(ctx)

        if control == 'end':
            self._index = len(self._pages) - 1
        elif control == 'start':
            self._index = 0
        else:
            self._index += control

        if self._index > len(self._pages) - 1 or self._index < 0:
            self._index = previous

        if self._index == previous:
            return

        if isinstance(self._pages[self._index], discord.Embed):
            await self.page.edit(embed=self._pages[self._index])
        else:
            await self.page.edit(content=self._pages[self._index])


def button(emoji: str, *, position: int = 666):
    """A decorator that adds a button to your interactive session class.

    Parameters
    -----------
    emoji: str
        The emoji to use as a button. This could be a unicode endpoint or in name:id format,
        for custom emojis.
    position: int
        The position to inject the button into.

    Raises
    -------
    TypeError
        The button callback is not a coroutine.
    """

    def deco(func):
        if not asyncio.iscoroutinefunction(func):
            raise TypeError('Button callback must be a coroutine.')

        func.__button__ = (emoji, func, position)
        return func

    return deco
