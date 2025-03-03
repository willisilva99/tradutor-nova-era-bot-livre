import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Modal, Button, TextInput
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker
import os

##################################
# CONFIGURAÇÃO BÁSICA DO BANCO (opcional)
##################################
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./local.db")  # Exemplo de fallback
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Se quiser criar tabelas para armazenar as configs, crie aqui.
# Exemplo (opcional):
# class TicketBuilderSettings(Base):
#     __tablename__ = "ticket_builder_settings"
#     guild_id = Column(String, primary_key=True)
#     title = Column(String, default="")
#     description = Column(String, default="")
#     image_url = Column(String, default="")
#     support_roles = Column(String, default="")
#     logs_channel = Column(String, default="")
#     eval_channel = Column(String, default="")
#
# Base.metadata.create_all(engine, checkfirst=True)

##################################
# MODAL DE CUSTOMIZAÇÃO
##################################
class TicketBuilderModal(Modal, title="Personalização do Ticket"):
    """
    Modal que coleta informações para personalizar o embed.
    """
    title_input = TextInput(
        label="Título",
        placeholder="Digite o título do ticket",
        required=True
    )
    description_input = TextInput(
        label="Descrição",
        style=discord.TextStyle.long,
        placeholder="Digite a descrição do ticket",
        required=True
    )
    image_url_input = TextInput(
        label="URL da Imagem/GIF (opcional)",
        placeholder="https://...",
        required=False
    )
    support_roles_input = TextInput(
        label="Cargos de Suporte (IDs separados por vírgula)",
        placeholder="Ex: 1234567890,0987654321",
        required=False
    )
    logs_channel_input = TextInput(
        label="Canal de Logs (ID, opcional)",
        placeholder="Ex: 11223344556677",
        required=False
    )
    eval_channel_input = TextInput(
        label="Canal de Avaliação (ID, opcional)",
        placeholder="Ex: 99887766554433",
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        """
        Ao enviar o modal, exibimos um embed de pré-visualização.
        Se quiser salvar no banco, basta inserir a lógica aqui.
        """
        # Se quiser armazenar no banco, faça algo como:
        # with SessionLocal() as session:
        #     settings = TicketBuilderSettings(
        #         guild_id=str(interaction.guild.id),
        #         title=self.title_input.value,
        #         description=self.description_input.value,
        #         image_url=self.image_url_input.value or "",
        #         support_roles=self.support_roles_input.value or "",
        #         logs_channel=self.logs_channel_input.value or "",
        #         eval_channel=self.eval_channel_input.value or ""
        #     )
        #     session.merge(settings)  # ou session.add(settings) se não existir
        #     session.commit()

        # Monta o embed de preview
        embed = discord.Embed(
            title=self.title_input.value,
            description=self.description_input.value,
            color=discord.Color.blue()
        )
        if self.image_url_input.value:
            embed.set_image(url=self.image_url_input.value)

        # Apenas para visualização
        embed.add_field(name="Cargos de Suporte", value=self.support_roles_input.value or "Nenhum", inline=False)
        embed.add_field(name="Canal de Logs", value=self.logs_channel_input.value or "Nenhum", inline=False)
        embed.add_field(name="Canal de Avaliação", value=self.eval_channel_input.value or "Nenhum", inline=False)

        # Envia resposta ephemeral com a pré-visualização
        await interaction.response.send_message(
            "✅ Configurações atualizadas! Veja a pré-visualização abaixo:",
            embed=embed,
            ephemeral=True
        )

##################################
# VIEW COM O BOTÃO QUE ABRE O MODAL
##################################
class TicketBuilderView(View):
    """
    Exibe um botão para abrir o modal de customização.
    """
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Customizar Ticket", style=discord.ButtonStyle.primary)
    async def open_modal(self, interaction: discord.Interaction, button: Button):
        """
        Ao clicar neste botão, abrimos o modal de customização.
        """
        await interaction.response.send_modal(TicketBuilderModal())

##################################
# COG PRINCIPAL
##################################
class TicketBuilderCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ticket_builder", description="Abre um painel para personalizar o ticket (apenas admins).")
    async def ticket_builder(self, interaction: discord.Interaction):
        """
        Responde com uma mensagem ephemeral + um botão. 
        Ao clicar no botão, o modal de customização é aberto.
        """
        # Verifica se o usuário é administrador
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                "❌ Somente administradores podem usar este comando.",
                ephemeral=True
            )

        # Responde de forma ephemeral com a view
        view = TicketBuilderView()
        await interaction.response.send_message(
            "Clique no botão abaixo para abrir a customização do ticket:",
            ephemeral=True,
            view=view
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(TicketBuilderCog(bot))
