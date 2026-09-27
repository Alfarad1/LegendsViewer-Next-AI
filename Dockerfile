# Build stage: .NET SDK + Node (Vue SPA is built via MSBuild npm targets)
FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

COPY LegendsViewer.Backend/LegendsViewer.Backend.csproj LegendsViewer.Backend/
COPY LegendsViewer.Frontend/LegendsViewer.Frontend.csproj LegendsViewer.Frontend/

RUN dotnet restore LegendsViewer.Backend/LegendsViewer.Backend.csproj

COPY LegendsViewer.Backend/ LegendsViewer.Backend/
COPY LegendsViewer.Frontend/ LegendsViewer.Frontend/

RUN dotnet publish LegendsViewer.Backend/LegendsViewer.Backend.csproj \
    -c Release \
    -o /app/publish \
    --no-restore

# Runtime stage
FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS final

RUN apt-get update \
    && apt-get install -y --no-install-recommends libfontconfig1 libfreetype6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=build /app/publish .

RUN mkdir -p /home/app/.config/LegendsViewer /data \
    && chown -R app:app /home/app /app /data

USER app

ENV ASPNETCORE_ENVIRONMENT=Production \
    HOME=/home/app \
    XDG_CONFIG_HOME=/home/app/.config

EXPOSE 15421 15422

ENTRYPOINT ["dotnet", "LegendsViewer.dll"]
