# Runtime build recovery, November 27

## Established incident evidence

- PR329 changed frontend and documentation only. Runtime configuration was
  unchanged from stable328.
- First deployment6d23283f contained the pip/npm build step but failed at
  Railway Create container with an unknown platform error. Its application
  container did not run; there were no application deploy logs.
- Same-configuration redeployb2eec22a produced a plan with Packages and Deploy,
  no pip/npm build step. It then crashed before migration/application startup
  because PIL was missing. This does not establish that Pillow installation
  failed, because no dependency installation step appeared in that build.
- Rollback to328 restored the already built image and variables. Health returned
  ok and approved library read70materials at01:54. No data migration or content
  changes were used in recovery.

## Reproduction and proposed fix

Railpack0.44.0 downloaded from its release and run locally against unchanged
main329 with no external build override generates a build step with no commands.
This reproduces the missing command boundary. It does not prove why the Railway
redeploy omitted its external override.

The proposed patch places an explicit build command in railpack.json and keeps
railway.toml pointing to the same checked-in shell script. Plan generation with
and without the external override produces that command and a deploy input
including the build output in both cases. The existing start command and Arabic
runtime preflight remain unchanged. Build now checks production-target imports,
runs the Arabic renderer check, builds the frontend and checks its output.

A separate Python3.13 CI job uses a clean /app/python-deps target and the same
shell script rather than the test environment's globally installed packages.
This verifies the target/import boundary and Arabic preflight. It is not a full
Railway image build or proof of platform container creation reliability.

No live retry is authorized by this document. Reviewed code and CI must pass
before another deployment. Stable328 is deliberately retained in production.

Sources: https://schema.railpack.com ; https://railpack.com/config/file/ ;
https://railpack.com/guides/adding-steps/ . Plan semantics checked with0.44.0.
