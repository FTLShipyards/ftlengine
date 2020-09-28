from invoke_release.tasks import *  # noqa: F403

configure_release_parameters(  # noqa: F405
    module_name='src',
    display_name='FTL',
    use_pull_request=True,
    use_tag=True,
)
