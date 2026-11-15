"""Synthetic policy for HTTP-generation tests; never a real authorization."""
from test_unified_model_budget import policy


def authorize_http_fake(client,models=None):
    config=policy();config.update(max_requests=100,max_images=100,max_images_per_request=20,
        max_output_tokens=client.max_output_tokens,reserve_tokens=200000,token_soft_limit=20000000,
        usd_stop='100',models=list(models or client.models),endpoints=[client.base_url])
    config['price'].update(endpoint=client.base_url,models=config['models'])
    client.budget.configure_model_budget(config,'JOB_http_fake')
    return client


def request_with_fake_budget(client,model,item,context):
    authorize_http_fake(client,[model])
    # These request-generation fixtures intentionally return {}. The real
    # ledger must stop for missing usage; the original wire assertions still run.
    from budget_manager import BudgetExceeded
    try:return client._request(model,item,dict(context,pid=1))
    except BudgetExceeded as exc:
        if str(exc)!='MODEL_USAGE_MISSING_OR_INVALID':raise
