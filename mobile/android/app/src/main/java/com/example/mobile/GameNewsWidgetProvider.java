package com.example.mobile;

import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.Context;
import android.content.SharedPreferences;
import android.widget.RemoteViews;

public class GameNewsWidgetProvider extends AppWidgetProvider {
    @Override
    public void onUpdate(Context context, AppWidgetManager appWidgetManager, int[] appWidgetIds) {
        for (int appWidgetId : appWidgetIds) {
            // Lấy dữ liệu được truyền từ Flutter thông qua HomeWidget plugin
            SharedPreferences prefs = context.getSharedPreferences("GameNewsWidget", Context.MODE_PRIVATE);
            String title = prefs.getString("title", "GameNews");
            String message = prefs.getString("message", "Đang tải dữ liệu...");

            RemoteViews views = new RemoteViews(context.getPackageName(), R.layout.widget_layout);
            views.setTextViewText(R.id.widget_title, title);
            views.setTextViewText(R.id.widget_message, message);

            appWidgetManager.updateAppWidget(appWidgetId, views);
        }
    }
}
