import { useQuery } from "@tanstack/react-query";
import { Link } from "expo-router";
import { FlatList, Pressable, StyleSheet, Text, View } from "react-native";

import { API_URL, type Driver, getJson } from "@/api";
import { usePullRefresh } from "@/use-pull-refresh";

// Until drivers log in, pick who you are from the list.
export default function DriversScreen() {
  const { data, error, refetch } = useQuery({
    queryKey: ["drivers"],
    queryFn: () => getJson<Driver[]>("/drivers"),
    refetchInterval: 30_000,
  });
  const pull = usePullRefresh(refetch);

  if (error) {
    return (
      <View style={styles.centred}>
        <Text style={styles.error}>{`Can't reach the API at ${API_URL}`}</Text>
        <Text>{error.message}</Text>
      </View>
    );
  }
  return (
    <FlatList
      data={data ?? []}
      keyExtractor={(driver) => String(driver.id)}
      contentInsetAdjustmentBehavior="automatic"
      refreshing={pull.refreshing}
      onRefresh={pull.onRefresh}
      renderItem={({ item }) => (
        <Link href={{ pathname: "/drivers/[id]", params: { id: item.id } }} asChild>
          <Pressable style={styles.row}>
            <Text style={styles.name}>{item.name}</Text>
            {item.vehicle_registration && (
              <Text style={styles.plate}>{item.vehicle_registration}</Text>
            )}
          </Pressable>
        </Link>
      )}
    />
  );
}

const styles = StyleSheet.create({
  centred: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24, gap: 8 },
  error: { fontWeight: "bold" },
  row: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    padding: 18,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderColor: "#ccc",
  },
  name: { fontSize: 18 },
  // Like a UK rear number plate, to match the live map
  plate: {
    backgroundColor: "#f7d117",
    borderWidth: 1,
    borderColor: "#111",
    borderRadius: 3,
    width: 92, // same size whatever the letters, like a real plate
    paddingVertical: 2,
    textAlign: "center",
    fontWeight: "700",
    letterSpacing: 0.5,
    overflow: "hidden",
  },
});
