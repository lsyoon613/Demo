"""Local CPU deployment: forward analysis only, with longer compute timeouts."""
from copy import deepcopy
from configs.module_config_full import module_config as original

module_config = deepcopy(original)
services = {
    "forward_wldn5": ("forward", 9501, "/wldn5_predict", 300),
    "impurity_predictor": ("impurity", 9691, "/impurity", 1800),
    "fast_filter": ("filter", 9611, "", 120),
    "atom_map_indigo": ("indigo", 9661, "/indigo_mapper", 120),
    "context_quarc": ("context", 9921, "/condition_prediction", 300),
}
module_config["global"]["require_frontend"] = False
for name in module_config["modules_to_start"]:
    module_config["modules_to_start"][name] = name in services
for name, (host, port, endpoint, timeout) in services.items():
    module_config[name]["deployment"].update(
        custom_prediction_url=f"http://{host}:{port}{endpoint}", timeout=timeout)
