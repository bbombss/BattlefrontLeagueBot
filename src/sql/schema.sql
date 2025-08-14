CREATE TABLE IF NOT EXISTS databaseSchema
(
    schemaVersion integer NOT NULL,
    PRIMARY KEY (schemaVersion)
);  

INSERT INTO databaseSchema(schemaVersion)
SELECT 0
WHERE
NOT EXISTS (
SELECT schemaVersion FROM databaseSchema
);

CREATE TABLE IF NOT EXISTS guilds
(
    guildId bigint NOT NULL,
    rank1Role bigint,
    rank2Role bigint,
    rank3Role bigint,
    rank0Role bigint,
    matchPingChannel bigint,
    PRIMARY KEY (guildId)
);

CREATE TABLE IF NOT EXISTS members
(
    userId bigint NOT NULL,
    guildId bigint NOT NULL,
    rank smallint,
    wins smallint,
    loses smallint,
    ties smallint,
    mu numeric(16, 14),
    sigma numeric(16, 14),
    PRIMARY KEY (userId, guildId),
    FOREIGN KEY (guildId) REFERENCES guilds (guildId)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS mapBans
(
    mapName text NOT NULL,
    guildId bigint NOT NULL,
    PRIMARY KEY (mapName, guildId),
    FOREIGN KEY (guildId) REFERENCES guilds (guildId)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS matches
(
    matchId bigint NOT NULL,
    guildId bigint NOT NULL,
    winnerData json NOT NULL,
    loserData json NOT NULL,
    matchTied bool NOT NULL DEFAULT false,
    matchDate timestamp,
    mapName text,
    PRIMARY KEY (matchId),
    FOREIGN KEY (guildId) REFERENCES guilds (guildId)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS memberAuditLog
(
    logId serial NOT NULL,
    userId bigint NOT NULL,
    guildId bigint NOT NULL,
    matchId bigint,
    won bool NOT NULL DEFAULT false,
    lost bool NOT NULL DEFAULT false,
    tied bool NOT NULL DEFAULT false,
    mu numeric(16, 14),
    sigma numeric(16, 14),
    PRIMARY KEY (logId),
    FOREIGN KEY (userId, guildId) REFERENCES members (userId, guildId)
        ON DELETE CASCADE,
    FOREIGN KEY (matchId) REFERENCES matches (matchId)
        ON DELETE CASCADE
);

-- Copyright (C) 2025 BBombs

-- This program is free software: you can redistribute it and/or modify
-- it under the terms of the GNU General Public License as published by
-- the Free Software Foundation, either version 3 of the License, or
-- (at your option) any later version.

-- This program is distributed in the hope that it will be useful,
-- but WITHOUT ANY WARRANTY; without even the implied warranty of
-- MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
-- GNU General Public License for more details.

-- You should have received a copy of the GNU General Public License
-- along with this program.  If not, see <https://www.gnu.org/licenses/>.