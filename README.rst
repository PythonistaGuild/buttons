A simple to use, highly customizable, Interactive Session and Paginator for discord.py.
Still in alpha stages, and rapid production. Feel free to suggest something via Discord.

Support
---------------------------
For support using Buttons, please join the official `support server
<http://discord.gg/JhW28zp>`_ on `Discord <https://discordapp.com/>`_.

Installation
---------------------------
**Buttons requires Python 3.6 or higher.**

**Windows**

.. code:: sh

    py -version -m pip install buttons

**Linux**

.. code:: sh

    python3 -m pip install buttons

Getting Started
----------------------------
A quick and easy paginator example:

.. code:: py3

    from discord.ext import commands
    from discord.ext import buttons


    class MyPaginator(buttons.Paginator):

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

        @buttons.button(emoji='\u23FA')
        async def record_button(self, ctx, member):
            await ctx.send('This button sends a silly message! But could be programmed to do much more.')

        @buttons.button(emoji='my_custom_emoji:1234567890')
        async def silly_button(self, ctx, member):
            await ctx.send('Beep boop...')


    bot = commands.Bot(command_prefix='??')


    @bot.command()
    async def test(ctx):
        pagey = MyPaginator(title='Silly Paginator', colour=0xc67862, embed=True, timeout=90, use_defaults=True,
                            entries=[1, 2, 3], length=1, format='**')

        await pagey.start(ctx)


    @bot.event
    async def on_ready():
        print('Ready!')


    bot.run('TOKEN')
