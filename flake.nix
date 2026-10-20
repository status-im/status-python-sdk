{
  description = "Status Python SDK";

  inputs = {
    # A channel URL: the exact revision is pinned in `flake.lock` and can be
    # moved forward with `nix flake update`.
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs =
    { self, nixpkgs }:
    let
      inherit (nixpkgs) lib;

      systems = lib.filter (system: lib.elem system nixpkgs.lib.systems.flakeExposed) [
        "x86_64-linux"
        "aarch64-linux"
        "aarch64-darwin"
      ];

      forAllSystems = lib.genAttrs systems;
      pkgsFor = system: nixpkgs.legacyPackages.${system};

      version = "1.4.0";

      release = {
        rev = "1.4.0";
        hash = "sha256-vNXGUaqJdzoCCVl/CnubBdR7TiVG94g+/FcFJAJSdUU=";
      };

      fetchRelease =
        pkgs:
        pkgs.fetchFromGitHub {
          owner = "status-im";
          repo = "status-python-sdk";
          rev = release.rev;
          hash = release.hash;
        };

      mkStatusSdk =
        {
          system,
          pname ? "status-sdk",
        }:
        let
          pkgs = pkgsFor system;

          # nixpkgs' `eth-utils` 6.0.0 imports `pydantic` at runtime but lists
          # it as a test dependency only, so `import eth_utils` fails without
          # it. `eth-abi` depends on `eth-utils` and the SDK depends on
          # `eth-abi`, so the missing transitive dependency is fixed here
          # instead of adding `pydantic` to the SDK's own dependencies.
          python = pkgs.python3.override {
            packageOverrides = pySelf: pySuper: {
              eth-utils = pySuper.eth-utils.overridePythonAttrs (old: {
                dependencies = old.dependencies ++ [ pySuper.pydantic ];
              });
            };
          };
        in
        python.pkgs.buildPythonPackage {
          inherit pname version;

          src = fetchRelease pkgs;

          format = "pyproject";
          build-system = [ python.pkgs.setuptools ];

          dependencies = with python.pkgs; [
            requests
            websocket-client
            websockets
            pandas
            pillow
            eth-abi
            pyyaml
            pycryptodome
          ];

          doCheck = false;

          pythonImportsCheck = [ "status_sdk" ];

          # at runtime the SDK writes into its own installation directory
          # (`assets/`, `data/`, `backups/`). That directory is read-only inside
          meta = {
            description = "Python SDK for the Status App backend (status-im/status-go)";
            homepage = "https://github.com/status-im/status-python-sdk";
            license = lib.licenses.mit;
            platforms = lib.platforms.unix;
            maintainers = [
              {
                name = "Nick Ninov";
                email = "nikolay@status.im";
              }
              {
                name = "Alexis Pentori";
                email = "alexis@status.im";
              }
            ];
          };
        };
    in
    {
      packages = forAllSystems (
        system:
        let
          base = mkStatusSdk { inherit system; };
        in
        {
          default = base;
          status-sdk = base;
        }
      );

      formatter = forAllSystems (system: (pkgsFor system).nixfmt);

      overlays.default = final: prev: {
        python3Packages = prev.python3Packages // {
          status-sdk = self.packages.${final.stdenv.hostPlatform.system}.status-sdk;
        };
      };

      devShells = forAllSystems (
        system:
        let
          pkgs = pkgsFor system;
          python = pkgs.python3;
          base = self.packages.${system}.status-sdk;
        in
        {
          default = pkgs.mkShell {
            name = "status-sdk-shell";
            packages = [
              (python.withPackages (ps: [ base ]))

              # Linting and testing.
              pkgs.ruff
              python.pkgs.mypy
              python.pkgs.pytest

              # Tools the SDK shells out to: Docker for `launch_docker_container`,
              # Nix and Git for `build_and_launch`.
              pkgs.docker-client
              pkgs.nix
              pkgs.git
              pkgs.curl
              pkgs.jq
              pkgs.gnumake
            ];

            shellHook = ''
              # Prefer the working tree over the packaged copy, so that edits are
              # picked up without reinstalling anything.
              if [ -d "$PWD/status_sdk" ]; then
                export PYTHONPATH="$PWD''${PYTHONPATH:+:$PYTHONPATH}"
              fi

              echo "status-sdk development shell"
              echo "  the SDK is importable: python3 -c 'import status_sdk'"
              echo "  linting:  ruff check . && ruff format --check ."
              echo "  the optional extras (agents, community-greet) are not packaged"
              echo "  in Nix - see the README for how to run the examples"
            '';
          };
        }
      );

      checks = forAllSystems (
        system:
        let
          pkgs = pkgsFor system;
          python = pkgs.python3;
          base = self.packages.${system}.status-sdk;
        in
        {
          default = base;

          import =
            pkgs.runCommand "status-sdk-import-check"
              {
                nativeBuildInputs = [ (python.withPackages (ps: [ base ])) ];
              }
              ''
                python3 -c "import status_sdk; print('status-sdk', status_sdk.__version__)"
                touch $out
              '';

          version =
            pkgs.runCommand "status-sdk-version-check"
              {
                nativeBuildInputs = [ python ];
                released = fetchRelease pkgs;
                flakeSrc = ./.;
                flakeVersion = version;
              }
              ''
                released="$released" flake_src="$flakeSrc" flake_version="$flakeVersion" python3 - <<'PY'
                import os, re, tomllib, pathlib

                def version(path):
                    return tomllib.loads(pathlib.Path(path).read_text())["project"]["version"]

                released = version(os.path.join(os.environ["released"], "pyproject.toml"))
                local = version(os.path.join(os.environ["flake_src"], "pyproject.toml"))
                flake = os.environ["flake_version"]

                assert released == local, f"released sources are {released}, pyproject.toml is {local}"
                assert released == flake, f"released sources are {released}, the flake is {flake}"

                changelog = pathlib.Path(os.path.join(os.environ["flake_src"], "CHANGELOG.md")).read_text()
                entry = r"^## \[" + re.escape(local) + r"\] - \d{4}-\d{2}-\d{2}$"
                assert re.search(entry, changelog, re.M), f"no changelog entry for {local}"
                PY
                touch $out
              '';

          dependencies =
            pkgs.runCommand "status-sdk-dependencies-check"
              {
                nativeBuildInputs = [ python ];
                flakeSrc = ./.;
                nixDependencies = builtins.concatStringsSep " " (map (dep: dep.pname) base.dependencies);
              }
              ''
                nix_dependencies="$nixDependencies" flake_src="$flakeSrc" python3 - <<'PY'
                import os, re, tomllib, pathlib

                pyproject = tomllib.loads(pathlib.Path(os.path.join(os.environ["flake_src"], "pyproject.toml")).read_text())
                declared = sorted(re.split(r"[^\w.-]", dep)[0] for dep in pyproject["project"]["dependencies"])
                packaged = sorted(os.environ["nix_dependencies"].split())

                assert packaged == declared, f"packaged dependencies {packaged} do not match pyproject.toml {declared}"
                PY
                touch $out
              '';
        }
      );
    };
}
