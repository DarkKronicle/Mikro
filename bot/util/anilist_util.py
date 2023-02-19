# https://github.com/lostb053/anibot/blob/e2ba9bc1cce89b1c3f8e179810234102e2834893/anibot/utils/data_parser.py

FAVORITE_ANIME = """
mutation ($id: Int) {
    ToggleFavourite (animeId: $id) {
        anime {
            pageInfo {
                total
            }
        }
    }
}   
"""

ANILIST_STATUS_MUTATION = """
mutation ($id: Int, $status: MediaListStatus) {
    SaveMediaListEntry (mediaId: $id, status: $status) {
        media {
            title {
                romaji
            }
        }
    }
}
"""

ANIME_QUERY = """
query ($id: Int, $idMal:Int, $search: String) {
    Media (id: $id, idMal: $idMal, search: $search, type: ANIME) {
        id
        idMal
        title {
            romaji
            english
            native
        }
        coverImage {
            extraLarge
        }
        format
        status
        episodes
        duration
        countryOfOrigin
        description
        startDate {
            year
            month
            day
        }
        endDate {
            year
            month
            day
        }
        source (version: 2)
        trailer {
            id
            site
        }
        genres
        tags {
            name
        }
        averageScore
        relations {
            edges {
                node {
                    title {
                        romaji
                        english
                    }
                    id
                    type
                }
                relationType
            }
        }
        nextAiringEpisode {
            timeUntilAiring
            episode
        }
        isAdult
        isFavourite
        mediaListEntry {
            status
            score
            id
        }
        siteUrl
    }
}
"""