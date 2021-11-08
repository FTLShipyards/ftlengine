from setuptools import setup
from src import __version__

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name="ftlengine",
    version=__version__,
    author="Jakob Daugherty",
    author_email="jakob.daugherty@quarkworks.co",
    description="A Docker based development and deployment engine",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Jakob-Daugherty/ftlengine",
    packages=[
        "src",
        "src.cli",
        "src.containers",
        "src.docker",
        "src.plugins",
        "src.utils",
        "src.exams",

    ],
    install_requires=[
        'attrs',
        'boto3',
        'botocore',
        'click',
        'docker',
        'dockerpty',
        'ntplib',  # Not sure if we need this
        'PyYAML',
        'requests',
        'scandir',
        'six',
        'urllib3==1.26.7',
    ],
    test_suite='tests',
    setup_requires=[
        'pytest-runner',
    ],
    tests_require=[
        'attrs',
        'click',
        'six',
        'pytest',
        'pytest-cov',
    ],
    entry_points='''
        [console_scripts]
        ftl = src.cli:cli

        [ftlengine.plugins]
        attach = src.plugins.attach:AttachPlugin
        boot = src.plugins.boot:BootPlugin
        build = src.plugins.build:BuildPlugin
        build_scripts = src.plugins.build_scripts:BuildScriptsPlugin
        chart = src.plugins.chart:ChartPlugin
        container = src.plugins.container:ContainerPlugin
        create = src.plugins.create:CreatePlugin
        doctor = src.plugins.doctor:DoctorPlugin
        domain_name = src.plugins.domain_name:DomainNamePlugin
        gc = src.plugins.gc:GcPlugin
        help = src.plugins.help:HelpPlugin
        hosts = src.plugins.hosts:HostsPlugin
        images = src.plugins.images:ImagesPlugin
        jump = src.plugins.jump:JumpPlugin
        legacy_env = src.plugins.legacy_env:LegacyEnvPlugin
        mounts = src.plugins.mounts:DevModesPlugin
        profile = src.plugins.profile:ProfilesPlugin
        ps = src.plugins.ps:PsPlugin
        registry = src.plugins.registry:RegistryPlugin
        aws = src.plugins.aws:AwsPlugin
        run = src.plugins.run:RunPlugin
        system = src.plugins.system:SystemContainerBuildPlugin
        tail = src.plugins.tail:TailPlugin
        volume = src.plugins.volume:VolumePlugin
        waits = src.plugins.waits:WaitsPlugin
        upgrade = src.plugins.upgrade:UpgradePlugin

        doctor_time = src.exams.doctor_time:DoctorTimePlugin
        doctor_connectivity = src.exams.doctor_connectivity:DoctorConnectivityPlugin
        doctor_docker_mac = src.exams.doctor_docker_mac:DoctorDockerMacPlugin
    ''',
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Intended Audience :: Developers",
        "Development Status :: 2 - Pre-Alpha",
    ],
    python_requires='>=3.6',
)
