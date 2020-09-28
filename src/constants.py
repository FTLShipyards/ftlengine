class PluginHook:
    INIT_GROUP_BUILD = "init-group-build"  # triggered right away when ftl build is executed
    PRE_GROUP_BUILD = "pre-group-build"    # triggered after ftl build has pulled images, before it builds images
    PRE_BUILD = "pre-build"                # triggered before each image is built
    POST_BUILD = "post-build"
    POST_GROUP_BUILD = "post-group-build"
    PRE_RUN_CONTAINER = "pre-run-container"
    POST_RUN_CONTAINER = "post-run-container"
    POST_RUN_CONTAINER_FULLY_STARTED = "post-run-container-fully-started"
    PRE_GROUP_START = "pre-group-start"
    POST_GROUP_START = "post-group-start"
    DOCKER_FAILURE = "docker-fail"
    CONTAINER_FAILURE = "container-fail"

    valid_hooks = frozenset([
        INIT_GROUP_BUILD,
        PRE_BUILD,
        POST_BUILD,
        PRE_RUN_CONTAINER,
        POST_RUN_CONTAINER,
        POST_RUN_CONTAINER_FULLY_STARTED,
        PRE_GROUP_BUILD,
        POST_GROUP_BUILD,
        PRE_GROUP_START,
        POST_GROUP_START,
        DOCKER_FAILURE,
        CONTAINER_FAILURE,
    ])
