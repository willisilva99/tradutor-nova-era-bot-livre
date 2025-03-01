    async def fetch_status_embed(self, server_key: str) -> discord.Embed:
        """
        Consulta as APIs do 7DTD e constrói um embed com:
          - Detalhes do servidor (nome, IP, porta, status, jogadores online)
          - Total de votos
          - Top 3 votantes
        Se ocorrer erro, retorna um embed de erro.
        """
        headers = {"Accept": "application/json"}
        detail_url = f"https://7daystodie-servers.com/api/?object=servers&element=detail&key={server_key}&format=json"
        votes_url = f"https://7daystodie-servers.com/api/?object=servers&element=votes&key={server_key}&format=json"
        voters_url = f"https://7daystodie-servers.com/api/?object=servers&element=voters&key={server_key}&month=current&format=json"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(detail_url, headers=headers) as r:
                    # Tenta converter para JSON, independentemente do mimetype
                    detail_data = await r.json(content_type=None)
            except Exception as e:
                print(f"Erro na consulta detail: {e}")
                return discord.Embed(
                    title="Erro ao obter dados do servidor",
                    description=f"Detail: {e}",
                    color=discord.Color.red()
                )
            try:
                async with session.get(votes_url, headers=headers) as r:
                    votes_data = await r.json(content_type=None)
            except Exception as e:
                print(f"Erro na consulta votes: {e}")
                return discord.Embed(
                    title="Erro ao obter dados de votos",
                    description=f"Votes: {e}",
                    color=discord.Color.red()
                )
            try:
                async with session.get(voters_url, headers=headers) as r:
                    voters_data = await r.json(content_type=None)
            except Exception as e:
                print(f"Erro na consulta voters: {e}")
                return discord.Embed(
                    title="Erro ao obter dados de votantes",
                    description=f"Voters: {e}",
                    color=discord.Color.red()
                )

        # Se detail_data estiver vazio, exibe embed de erro
        if not detail_data:
            return discord.Embed(
                title="Erro ao obter dados do servidor",
                description="A API não retornou informações. Verifique a chave e tente novamente.",
                color=discord.Color.red()
            )

        # Extração dos dados (ajuste conforme a estrutura real da API)
        server_name = detail_data.get("serverName", "N/A")
        ip = detail_data.get("address", "N/A")
        port = detail_data.get("port", "N/A")
        players = detail_data.get("players", 0)
        max_players = detail_data.get("maxplayers", 0)
        online_status = detail_data.get("is_online", "0") == "1"
        status_text = "Online" if online_status else "Offline"

        total_votes = votes_data.get("votes", "N/A")
        # Processa a lista de votantes para pegar os top 3
        voters_list = voters_data.get("voters", [])
        voters_sorted = sorted(voters_list, key=lambda v: v.get("votes", 0), reverse=True)
        top3 = voters_sorted[:3]
        top3_str = ", ".join(f'{v.get("username", "N/A")} ({v.get("votes", 0)})' for v in top3) if top3 else "N/A"

        embed = discord.Embed(
            title=f"Status do Servidor: {server_name}",
            color=discord.Color.dark_green() if online_status else discord.Color.red()
        )
        embed.add_field(name="Status", value=status_text, inline=True)
        embed.add_field(name="IP:Porta", value=f"{ip}:{port}", inline=True)
        embed.add_field(name="Jogadores Online", value=f"{players}/{max_players}", inline=True)
        embed.add_field(name="Total de Votos", value=total_votes, inline=True)
        embed.add_field(name="Top 3 Votantes", value=top3_str, inline=False)
        embed.set_footer(text="Atualizado em " + time.strftime("%d/%m/%Y %H:%M:%S"))
        return embed
