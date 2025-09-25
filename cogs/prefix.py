import nextcord
from nextcord.ext import commands
import sqlite3
import os
import asyncio
from typing import List, Dict, Set
import json


class DynamicPrefix(commands.Cog, name="Dynamic Prefix"):

    def __init__(self, bot):
        self.bot = bot

        self.prefix_cache: Dict[int, Set[str]] = {}
        self.default_prefix = "i."
        self.setup_database()
        self.load_prefixes()

        self.bot.command_prefix = self.get_prefix

    def setup_database(self):
        """Set up the SQLite database and required tables"""

        if not os.path.exists("db"):
            os.makedirs("db")

        with sqlite3.connect("db/prefixes.db") as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
            CREATE TABLE IF NOT EXISTS guild_prefixes (
                guild_id INTEGER,
                prefix TEXT,
                PRIMARY KEY (guild_id, prefix)
            )
            """
            )
            conn.commit()

    def load_prefixes(self):
        """Load all prefixes from the database into the cache"""
        with sqlite3.connect("db/prefixes.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT guild_id, prefix FROM guild_prefixes")

            for (
                guild_id,
                prefix_val,
            ) in (
                cursor.fetchall()
            ):  # Renamed 'prefix' to 'prefix_val' to avoid conflict
                if guild_id not in self.prefix_cache:
                    self.prefix_cache[guild_id] = set()
                self.prefix_cache[guild_id].add(prefix_val)

    async def get_prefix(self, bot, message):
        """Dynamic prefix getter for the bot"""

        if message.guild is None:
            return self.default_prefix

        guild_id = message.guild.id

        prefixes = [self.default_prefix]

        if guild_id in self.prefix_cache and self.prefix_cache[guild_id]:
            prefixes.extend(list(self.prefix_cache[guild_id]))

        return prefixes

    def add_prefix_to_db(
        self, guild_id: int, prefix_val: str
    ) -> bool:  # Renamed 'prefix' to 'prefix_val'
        """Add a prefix to the database if it doesn't exist already"""
        try:
            with sqlite3.connect("db/prefixes.db") as conn:
                cursor = conn.cursor()

                cursor.execute(
                    "SELECT 1 FROM guild_prefixes WHERE guild_id = ? AND prefix = ?",
                    (guild_id, prefix_val),
                )
                if cursor.fetchone():
                    return False

                cursor.execute(
                    "INSERT INTO guild_prefixes (guild_id, prefix) VALUES (?, ?)",
                    (guild_id, prefix_val),
                )
                conn.commit()

                if guild_id not in self.prefix_cache:
                    self.prefix_cache[guild_id] = set()
                self.prefix_cache[guild_id].add(prefix_val)
                return True
        except sqlite3.Error as e:
            print(f"Database error: {e}")
            return False

    def remove_prefix_from_db(
        self, guild_id: int, prefix_val: str
    ) -> bool:  # Renamed 'prefix' to 'prefix_val'
        """Remove a specific prefix from the database"""
        try:
            with sqlite3.connect("db/prefixes.db") as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM guild_prefixes WHERE guild_id = ? AND prefix = ?",
                    (guild_id, prefix_val),
                )
                conn.commit()

                if cursor.rowcount > 0:

                    if (
                        guild_id in self.prefix_cache
                        and prefix_val in self.prefix_cache[guild_id]
                    ):
                        self.prefix_cache[guild_id].remove(prefix_val)
                    return True
                return False
        except sqlite3.Error as e:
            print(f"Database error: {e}")
            return False

    def get_all_prefixes(self, guild_id: int) -> List[str]:
        """Get all prefixes for a specific guild"""
        if guild_id in self.prefix_cache:
            return [self.default_prefix] + list(self.prefix_cache[guild_id])
        return [self.default_prefix]

    @commands.group(invoke_without_command=True, case_insensitive=True)
    async def prefix(self, ctx: commands.Context):
        """Manages server-specific command prefixes."""
        if ctx.invoked_subcommand is None:
            await ctx.invoke(self.list_prefixes)  # Call the list subcommand

    @prefix.command(name="add")
    @commands.has_permissions(administrator=True)
    async def add_new_prefix(self, ctx: commands.Context, new_prefix: str):
        """Add a custom prefix for the server (Admin only).
        Example: `i.prefix add !`
        """
        if not new_prefix:
            await ctx.send("Prefix cannot be empty.")
            return

        if len(new_prefix) > 10:
            await ctx.send("Prefix is too long. Maximum length is 10 characters.")
            return

        prefixes = self.get_all_prefixes(ctx.guild.id)
        # We check for 10 because default prefix is always there, users can add up to 9 custom.
        if len(prefixes) >= 10:
            await ctx.send(
                "Maximum number of custom prefixes reached (9). Please remove some before adding more."
            )
            return

        if new_prefix == self.default_prefix and self.default_prefix in prefixes:
            await ctx.send(
                f"Prefix `{new_prefix}` is the default prefix and cannot be added again."
            )
            return

        success = self.add_prefix_to_db(ctx.guild.id, new_prefix)

        if success:
            await ctx.send(f"Prefix `{new_prefix}` added successfully.")
        else:
            await ctx.send(f"Prefix `{new_prefix}` already exists.")

    @prefix.command(name="remove", aliases=["delete"])
    @commands.has_permissions(administrator=True)
    async def remove_existing_prefix(
        self, ctx: commands.Context, prefix_to_remove: str
    ):
        """Delete a specific custom prefix for the server (Admin only).
        Example: `i.prefix remove !`
        """
        if prefix_to_remove == self.default_prefix:
            await ctx.send(f"Cannot remove the default prefix `{self.default_prefix}`.")
            return

        success = self.remove_prefix_from_db(ctx.guild.id, prefix_to_remove)

        if success:
            await ctx.send(f"Prefix `{prefix_to_remove}` removed successfully.")
        else:
            await ctx.send(
                f"Prefix `{prefix_to_remove}` not found or is not a custom prefix."
            )

    @prefix.command(name="clear")
    @commands.has_permissions(administrator=True)
    async def clear_all_prefixes(self, ctx: commands.Context):
        """Remove all custom prefixes for this server (Admin only).
        The default prefix will remain.
        Example: `i.prefix clear`
        """
        try:
            with sqlite3.connect("db/prefixes.db") as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM guild_prefixes WHERE guild_id = ?", (ctx.guild.id,)
                )
                conn.commit()

                if ctx.guild.id in self.prefix_cache:
                    self.prefix_cache[ctx.guild.id] = (
                        set()
                    )  # Clear custom prefixes from cache

                await ctx.send(
                    f"All custom prefixes removed. Using default prefix `{self.default_prefix}`."
                )
        except sqlite3.Error as e:
            await ctx.send(f"Error clearing prefixes: {e}")

    @prefix.command(name="list", aliases=["show"])
    async def list_prefixes(self, ctx: commands.Context):
        """Show all current prefixes for this server.
        Example: `i.prefix list`
        """
        current_prefixes = self.get_all_prefixes(ctx.guild.id)

        if len(current_prefixes) == 1 and current_prefixes[0] == self.default_prefix:
            await ctx.send(
                f"Only the default prefix is active: `{self.default_prefix}`"
            )
        else:
            prefix_list_str = "\n".join(
                [
                    f"• `{p}`" + (" (default)" if p == self.default_prefix else "")
                    for p in current_prefixes
                ]
            )
            embed = nextcord.Embed(
                title=f"Prefixes for {ctx.guild.name}",
                description=f"The following prefixes are active:\n{prefix_list_str}",
                color=0x3498DB,  # A nice blue color
            )
            await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        """Clean up prefixes when bot leaves a guild"""
        try:
            with sqlite3.connect("db/prefixes.db") as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM guild_prefixes WHERE guild_id = ?", (guild.id,)
                )
                conn.commit()

            if guild.id in self.prefix_cache:
                del self.prefix_cache[guild.id]
        except sqlite3.Error as e:
            print(f"Error cleaning up prefixes for guild {guild.id}: {e}")

    # @commands.Cog.listener()
    # async def on_message(self, message):
    #     """Process commands with the dynamic prefix"""
    #     pass


def setup(bot):
    bot.add_cog(DynamicPrefix(bot))
