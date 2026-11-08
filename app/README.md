# Fleetwatch driver app

An Expo (React Native) app for drivers: pick yourself from the list to see your 7-day score and the figures behind it.

## Running it on your phone

1. Install **Expo Go** from the App Store or Play Store.
2. Start the API so the phone can reach it (from the repo root):

   ```sh
   uv run fastapi dev src/fleetwatch/main.py --host 0.0.0.0
   ```

3. Start the app, then scan the QR code with your phone's camera (iOS) or Expo Go (Android):

   ```sh
   cd app && npm install && npx expo start
   ```

The phone and the computer need to be on the same Wi-Fi. The app finds the API on the machine running `expo start`, port 8000; set `EXPO_PUBLIC_API_URL` in `app/.env.local` to use another address.

`npx expo start --web` runs it in a browser instead.

## Checks

```sh
npm run typecheck
npx expo lint
```
