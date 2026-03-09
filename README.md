# lightweightvk_screenshot_tests

Reference screenshots for LightweightVK CI screenshot tests.

## Structure

```
references/
  ubuntu/          # Reference images for Ubuntu CI (Mesa swrast)
    001_HelloTriangle.png
    005_MeshShaders.png
```

## Updating reference images

1. Run the CI workflow (or run samples locally in headless mode)
2. Download the `LogsAndScreenshots` artifact
3. Copy the rendered PNGs into `references/ubuntu/`
4. Commit and push to this repository
5. Update the `revision` hash in `third-party/bootstrap-deps.json` in the main repo
