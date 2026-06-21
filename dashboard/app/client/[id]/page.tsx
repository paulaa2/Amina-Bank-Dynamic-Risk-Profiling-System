import ClientDossierPage from "./client-page";

export async function generateStaticParams() {
  return [
    { id: "1" },
    { id: "2" },
    { id: "3" },
    { id: "4" },
    { id: "5" },
    { id: "6" },
    { id: "7" },
  ];
}

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  return <ClientDossierPage params={params} />;
}
