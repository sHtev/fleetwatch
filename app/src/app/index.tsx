import { useQuery } from "@tanstack/react-query";
import { Link } from "expo-router";
import { FlatList, Pressable, StyleSheet, Text, View } from "react-native";

import { API_URL, type Driver, getJson } from "@/api";

// Until drivers log in, pick who you are from the list.
export default function DriversScreen() {
  const { data, error, isFetching, refetch } = useQuery({
    queryKey: ["drivers"],
    queryFn: () => getJson<Driver[]>("/drivers"),
  });

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
      refreshing={isFetching}
      onRefresh={() => void refetch()}
      renderItem={({ item }) => (
        <Link href={{ pathname: "/drivers/[id]", params: { id: item.id } }} asChild>
          <Pressable style={styles.row}>
            <Text style={styles.name}>{item.name}</Text>
          </Pressable>
        </Link>
      )}
    />
  );
}

const styles = StyleSheet.create({
  centred: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24, gap: 8 },
  error: { fontWeight: "bold" },
  row: { padding: 18, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: "#ccc" },
  name: { fontSize: 18 },
});
