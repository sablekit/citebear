import { Chat } from "@/components/chat";
import { fetchLibrary } from "@/lib/library";

export default async function Home() {
  const documents = await fetchLibrary();
  return <Chat documents={documents} />;
}
