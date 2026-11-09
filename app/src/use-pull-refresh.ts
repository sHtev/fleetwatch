import { useState } from "react";

// Shows the pull-to-refresh spinner only when the user pulls, not during background polling.
export function usePullRefresh(refetch: () => Promise<unknown>) {
  const [refreshing, setRefreshing] = useState(false);
  const onRefresh = async () => {
    setRefreshing(true);
    await refetch();
    setRefreshing(false);
  };
  return { refreshing, onRefresh: () => void onRefresh() };
}
