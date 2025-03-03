const { ActionRowBuilder, ButtonBuilder, ButtonStyle, SlashCommandBuilder, EmbedBuilder, PermissionsBitField } = require('discord.js');

module.exports = {
    data: new SlashCommandBuilder()
        .setName('ban')
        .setDescription('Bane um usuário do servidor.')
        .addUserOption(option =>
            option.setName('target')
                .setDescription('Usuário a ser banido.')
                .setRequired(true))
        .addStringOption(option =>
            option.setName('reason')
                .setDescription('Motivo do banimento.')
                .setRequired(false)),

    async execute(interaction) {
        // Verifica se o usuário tem permissão de administrador
        if (!interaction.member.permissions.has(PermissionsBitField.Flags.BanMembers)) {
            return await interaction.reply({
                content: "❌ **Você não tem permissão para banir membros!**",
                ephemeral: true
            });
        }

        const target = interaction.options.getUser('target');
        const reason = interaction.options.getString('reason') ?? 'Sem motivo informado.';

        // Verifica se o usuário tentou se banir
        if (target.id === interaction.user.id) {
            return await interaction.reply({
                content: "❌ **Você não pode se banir!**",
                ephemeral: true
            });
        }

        // Cria os botões de confirmação
        const confirmButton = new ButtonBuilder()
            .setCustomId('confirm_ban')
            .setLabel('✅ Confirmar Banimento')
            .setStyle(ButtonStyle.Danger);

        const cancelButton = new ButtonBuilder()
            .setCustomId('cancel_ban')
            .setLabel('❌ Cancelar')
            .setStyle(ButtonStyle.Secondary);

        const row = new ActionRowBuilder()
            .addComponents(cancelButton, confirmButton);

        const embed = new EmbedBuilder()
            .setTitle("⚠️ Confirmação de Banimento")
            .setDescription(`Tem certeza de que deseja banir **${target.tag}**?`)
            .addFields({ name: "Motivo:", value: reason })
            .setColor('Red')
            .setFooter({ text: `Ação solicitada por ${interaction.user.tag}`, iconURL: interaction.user.displayAvatarURL() });

        // Envia a mensagem com os botões
        await interaction.reply({
            embeds: [embed],
            components: [row],
            ephemeral: true
        });

        // Filtro para capturar cliques nos botões
        const filter = i => i.user.id === interaction.user.id;

        // Criando o coletor para aguardar resposta
        const collector = interaction.channel.createMessageComponentCollector({ filter, time: 15000 });

        collector.on('collect', async i => {
            if (i.customId === 'confirm_ban') {
                try {
                    const member = await interaction.guild.members.fetch(target.id);
                    await member.ban({ reason });

                    const successEmbed = new EmbedBuilder()
                        .setTitle("🔨 Usuário Banido")
                        .setDescription(`✅ **${target.tag}** foi banido com sucesso!`)
                        .addFields({ name: "Motivo:", value: reason })
                        .setColor('Green')
                        .setFooter({ text: `Ação confirmada por ${interaction.user.tag}`, iconURL: interaction.user.displayAvatarURL() });

                    await interaction.editReply({
                        embeds: [successEmbed],
                        components: []
                    });

                } catch (error) {
                    console.error(error);
                    await interaction.editReply({
                        content: "❌ **Não foi possível banir esse usuário.** Verifique minhas permissões e tente novamente.",
                        components: []
                    });
                }
            } else if (i.customId === 'cancel_ban') {
                await interaction.editReply({
                    content: "🚫 **Ação cancelada! O usuário não foi banido.**",
                    components: []
                });
            }
        });

        collector.on('end', async collected => {
            if (collected.size === 0) {
                await interaction.editReply({
                    content: "⌛ **Tempo esgotado! O banimento não foi confirmado.**",
                    components: []
                });
            }
        });
    }
};
