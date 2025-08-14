DROP TABLE maps;
ALTER TABLE members ADD mu numeric(16, 14);
ALTER TABLE members ADD sigma numeric(16, 14);
UPDATE members SET rank = 0;
ALTER TABLE guilds ADD rank0Role bigint;
ALTER TABLE guilds ADD matchPingChannel bigint;