import { useQuery } from "@tanstack/react-query";
import { useLocalSearchParams } from "expo-router";
import { RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";

import { type DriverScore, getJson } from "@/api";
import { usePullRefresh } from "@/use-pull-refresh";

function scoreColour(score: number): string {
  if (score >= 85) return "#1a9850";
  if (score >= 60) return "#f39c12";
  return "#d7301f";
}

// The driver's 7-day score, and the figures behind it so they can see why.
export default function ScoreScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { data, dataUpdatedAt, error, refetch } = useQuery({
    queryKey: ["drivers", id, "score"],
    queryFn: () => getJson<DriverScore>(`/drivers/${id}/score`),
    refetchInterval: 10_000, // fresh while the screen is open
  });
  const pull = usePullRefresh(refetch);

  return (
    <ScrollView
      contentInsetAdjustmentBehavior="automatic"
      contentContainerStyle={styles.container}
      refreshControl={<RefreshControl {...pull} />}
    >
      {error && <Text>{error.message}</Text>}
      {data && (
        <>
          <Text style={[styles.score, { color: scoreColour(data.score) }]}>
            {Math.round(data.score)}
          </Text>
          <Text style={styles.caption}>out of 100, over the last 7 days</Text>
          <View style={styles.figures}>
            <Figure label="Distance" value={`${data.distance_miles.toFixed(0)} miles`} />
            <Figure label="Driving time" value={`${(data.driving_minutes / 60).toFixed(1)} hours`} />
            <Figure
              label="Harsh braking or acceleration"
              value={`${data.harsh_events} (${data.harsh_per_100_miles} per 100 miles)`}
            />
            <Figure label="Time over the speed limit" value={`${data.speeding_percent}%`} />
          </View>
          <Text style={styles.updated}>
            Updated {new Date(dataUpdatedAt).toLocaleTimeString("en-GB")}
          </Text>
        </>
      )}
    </ScrollView>
  );
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.figure}>
      <Text style={styles.label}>{label}</Text>
      <Text style={styles.value}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { padding: 24 },
  score: { alignSelf: "center", fontSize: 96, fontWeight: "bold" },
  caption: { alignSelf: "center", color: "#666", marginBottom: 24 },
  figures: { gap: 12 },
  figure: { flexDirection: "row", justifyContent: "space-between", gap: 12 },
  label: { flexShrink: 1, color: "#444" },
  value: { fontWeight: "600" },
  updated: { alignSelf: "center", color: "#999", marginTop: 24, fontSize: 12 },
});
