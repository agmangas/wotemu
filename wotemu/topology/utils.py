from wotemu.enums import NetworkConditions, NodePlatforms


def platform_to_resources(platform):
    if platform not in NodePlatforms:
        raise ValueError("Unknown node platform")

    raise NotImplementedError


def conditions_to_netem(condition):
    if condition not in NetworkConditions:
        raise ValueError("Unknown network condition")

    netem_map = {
        NetworkConditions.THREEG: [
            "delay --time 100 --jitter 50 --distribution normal",
            "rate --rate 200kbit"
        ],
        NetworkConditions.WIFI: [
            "delay --time 15 --jitter 10 --distribution normal"
        ],
        NetworkConditions.CABLE: [
            "delay --time 5 --jitter 1 --distribution normal"
        ]
    }

    return netem_map.get(condition, None)
