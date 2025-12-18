def normalize_bool(val):
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ["true", "yes", "1"]
    return False


def validate_answer(example, pred, trace=None):
    if not hasattr(pred, 'useful'):
        return False
        
    pred_val = pred.useful
    true_val = example.useful

    return normalize_bool(pred_val) == normalize_bool(true_val)