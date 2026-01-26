USER_NAME_TO_NAME_MAP = {"Sam": "fuqyou", "Lewis": "homicides.", "Gobbo": "gobboo", "Nathan": "quantix.dev", "Sam": "frenfrog_", "Tom": "tomass__", "Cam": "camisasleep", "Wayne": "lookathimtremble", "Jake": "jake7917", "Mia": ".lovi.", "Lukasz": "xmistyxo"}


def user_name_to_name(user_name: str):
    result = [key for key, x in USER_NAME_TO_NAME_MAP.items() if x == user_name]
    return result[0] if result else user_name
