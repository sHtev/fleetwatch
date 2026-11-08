import Constants from "expo-constants";

// The phone can't reach "localhost" on the Mac. Use EXPO_PUBLIC_API_URL if set, otherwise
// the dev server's host (the Mac running `expo start`) on the API's port.
function apiUrl(): string {
  if (process.env.EXPO_PUBLIC_API_URL) return process.env.EXPO_PUBLIC_API_URL;
  const host = Constants.expoConfig?.hostUri?.split(":")[0] ?? "localhost";
  return `http://${host}:8000`;
}

export const API_URL = apiUrl();

export type Driver = { id: number; name: string };

export type DriverScore = {
  driver_id: number;
  since: string;
  until: string;
  score: number;
  distance_miles: number;
  driving_minutes: number;
  harsh_events: number;
  harsh_per_100_miles: number;
  speeding_percent: number;
};

export async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`);
  if (!response.ok) throw new Error(`${response.status} from ${path}`);
  return response.json() as Promise<T>;
}
